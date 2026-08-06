from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.db.models import LessonNoteModel, SessionModel, SkillModel
from app.domain.errors import ToolValidationError
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.skills import fuzzy_match_skill


class RiskTier(StrEnum):
    READ = "read"
    WRITE_AUTO = "write_auto"
    WRITE_CONFIRM = "write_confirm"


class Assessment(StrEnum):
    GOOD = "good"
    OK = "ok"
    NEEDS_ATTENTION = "needs_attention"
    NOT_PRACTICED = "not_practiced"


@dataclass
class ToolContext:
    """Per-message dependencies handed to every tool: repos + a clock."""

    sessions: SessionRepository
    skills: SkillRepository
    notes: LessonNoteRepository
    audit: AuditLogRepository
    timezone: ZoneInfo

    def today(self) -> date:
        return datetime.now(self.timezone).date()


class ToolParams(BaseModel):
    """Base for tool parameter models."""


class GetNextLessonsParams(ToolParams):
    days_ahead: int = Field(default=14, ge=1, le=90)


class GetLessonHistoryParams(ToolParams):
    limit: int = Field(default=10, ge=1, le=50)


class LessonItem(BaseModel):
    skill: str = Field(
        description="Skill name in English, from the skills list the assistant knows"
    )
    assessment: Assessment
    note: str


class LogLessonParams(ToolParams):
    date: str = Field(default="today", description="ISO date YYYY-MM-DD, or 'today'")
    skills: list[LessonItem] = Field(default_factory=list)
    general_note: str | None = None

    @field_validator("date")
    @classmethod
    def _validate_date(cls, value: str) -> str:
        if value == "today":
            return value
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be ISO YYYY-MM-DD or 'today'") from exc
        return value


class Tool(Protocol):
    name: str
    description: str
    tier: RiskTier

    def openai_schema(self) -> dict[str, Any]: ...

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]: ...


def _serialize_session(
    model: SessionModel, notes: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "id": model.id,
        "date": model.date.isoformat(),
        "start_time": model.start_time,
        "end_time": model.end_time,
        "instructor": model.instructor,
        "lesson_type": model.lesson_type,
        "status": model.status,
        "source": model.source,
        "notes": notes or [],
    }


def _serialize_note(note_model: LessonNoteModel, skill: SkillModel | None) -> dict[str, Any]:
    return {
        "id": note_model.id,
        "skill_id": note_model.skill_id,
        "skill": skill.name if skill else None,
        "skill_category": skill.category if skill else None,
        "assessment": note_model.assessment,
        "note": note_model.note,
        "created_at": note_model.created_at.isoformat() if note_model.created_at else None,
    }


class GetNextLessonsTool:
    name = "get_next_lessons"
    description = (
        "List upcoming scheduled driving lessons within days_ahead days from today. "
        "Returns id, date, start_time, end_time, instructor, lesson_type, status."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetNextLessonsParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetNextLessonsParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        sessions = await ctx.sessions.get_upcoming(ctx.today(), params.days_ahead)
        return {
            "tool": self.name,
            "count": len(sessions),
            "sessions": [_serialize_session(s) for s in sessions],
        }


class GetLessonHistoryTool:
    name = "get_lesson_history"
    description = (
        "List the most recent past lessons (date < today) with their notes. "
        "Each session includes id, date, instructor, status and its notes "
        "(id, skill, assessment, note, created_at). Use this for 'what did we do on <date>' "
        "and 'what did we do last time'."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetLessonHistoryParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetLessonHistoryParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        sessions = await ctx.sessions.get_history(ctx.today(), params.limit)
        out: list[dict[str, Any]] = []
        for session_model in sessions:
            note_models = await ctx.sessions.notes_for(session_model.id)
            notes: list[dict[str, Any]] = []
            for note_model in note_models:
                skill = await ctx.skills.get(note_model.skill_id) if note_model.skill_id else None
                notes.append(_serialize_note(note_model, skill))
            out.append(_serialize_session(session_model, notes))
        return {"tool": self.name, "count": len(sessions), "sessions": out}


class LogLessonTool:
    name = "log_lesson"
    description = (
        "Log what was practiced in a lesson. Auto-approved write. "
        "Pass the date (ISO YYYY-MM-DD or 'today'), a list of skills each with an assessment "
        "(good|ok|needs_attention|not_practiced) and a short note, and an optional general_note. "
        "Skill names are fuzzy-matched to the skills list; unmatched skills become general notes "
        "and are flagged in the reply. Returns created note ids and matched/unmatched skills."
    )
    tier = RiskTier.WRITE_AUTO

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": LogLessonParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = LogLessonParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc

        # Idempotency: if this exact key was processed before, return the stored result.
        if idempotency_key is not None:
            prior = await ctx.audit.get_by_idempotency_key(idempotency_key)
            if prior is not None:
                return dict(prior.payload)  # type: ignore[arg-type]

        lesson_date = ctx.today() if params.date == "today" else date.fromisoformat(params.date)

        # Find or create a session for this date. Prefer an existing session (e.g. an email
        # booking); if none, create a manual completed session.
        existing = await ctx.sessions.get_by_date(lesson_date)
        if existing:
            session_model = existing[0]
        else:
            session_model = await ctx.sessions.create(
                date=lesson_date, status="completed", source="manual"
            )

        all_skills = await ctx.skills.all()
        note_ids: list[int] = []
        matched: list[dict[str, Any]] = []
        unmatched: list[str] = []
        for item in params.skills:
            skill = fuzzy_match_skill(item.skill, all_skills)
            if skill is not None:
                note = await ctx.notes.create(
                    session_id=session_model.id,
                    skill_id=skill.id,
                    note=item.note,
                    assessment=item.assessment.value,
                )
                note_ids.append(note.id)
                matched.append(
                    {"skill": skill.name, "category": skill.category, "note_id": note.id}
                )
            else:
                # Unmatched skill -> store as a general note (skill_id=None) and flag it.
                note = await ctx.notes.create(
                    session_id=session_model.id,
                    skill_id=None,
                    note=item.note,
                    assessment=item.assessment.value,
                )
                note_ids.append(note.id)
                unmatched.append(item.skill)

        general_note_id: int | None = None
        if params.general_note:
            gen = await ctx.notes.create(
                session_id=session_model.id,
                skill_id=None,
                note=params.general_note,
                assessment=None,
            )
            general_note_id = gen.id
            note_ids.append(gen.id)

        result: dict[str, Any] = {
            "tool": self.name,
            "session_id": session_model.id,
            "date": lesson_date.isoformat(),
            "note_ids": note_ids,
            "matched_skills": matched,
            "unmatched_skills": unmatched,
            "general_note_id": general_note_id,
        }

        await ctx.audit.create(
            action="log_lesson",
            payload=result,
            idempotency_key=idempotency_key,
        )
        return result


def phase1_tools() -> list[Tool]:
    """The Phase 1 tool registry: the skeleton only ships these three."""
    return [GetNextLessonsTool(), GetLessonHistoryTool(), LogLessonTool()]


def tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def dump_tool_result(result: dict[str, Any]) -> str:
    """Compact JSON for the message history / guardrail containment check."""
    return json.dumps(result, default=str, ensure_ascii=False)
