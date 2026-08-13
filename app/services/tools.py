from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.db.models import LessonNoteModel, SessionModel, SkillModel
from app.domain.errors import ToolValidationError
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository, NoteWithContext
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.knowledge import CbrTopic, KnowledgeBase
from app.services.semantic import SkillStatus, is_stale, pace, skill_status
from app.services.skills import fuzzy_match_skill
from app.services.web_search import WebSearcher, serialize_web_results


class RiskTier(StrEnum):
    READ = "read"
    WRITE_AUTO = "write_auto"
    WRITE_CONFIRM = "write_confirm"


class Assessment(StrEnum):
    GOOD = "good"
    OK = "ok"
    NEEDS_ATTENTION = "needs_attention"
    NOT_PRACTICED = "not_practiced"


class LessonType(StrEnum):
    """The kind of lesson a session records (spec: rijles|proefles|exam)."""

    RIJLES = "rijles"  # a normal lesson (default)
    PROEFLES = "proefles"  # a trial / mock lesson
    EXAM = "exam"  # the real CBR practical exam


class SkillCategory(StrEnum):
    """The seven CBR competency categories (spec section 4 / seed.py)."""

    VEHICLE_CONTROL = "Vehicle control"
    OBSERVATION = "Observation"
    INTERSECTIONS = "Intersections"
    HIGHWAY = "Highway"
    SPECIAL_MANEUVERS = "Special maneuvers"
    INDEPENDENT_DRIVING = "Independent driving"
    ATTITUDE = "Attitude & environment"


@dataclass
class ToolContext:
    """Per-message dependencies handed to every tool: repos + a clock + services."""

    sessions: SessionRepository
    skills: SkillRepository
    notes: LessonNoteRepository
    audit: AuditLogRepository
    timezone: ZoneInfo
    knowledge: KnowledgeBase
    web: WebSearcher
    exam_date: date | None = None

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
        "List the most recent past lessons (date <= today) with their notes. "
        "A same-day completed lesson is included. Each session includes id, date, "
        "instructor, status and its notes (id, skill, assessment, note, created_at). "
        "Use this for 'what did we do on <date>' and 'what are my notes from today?'."
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

        today = ctx.today()
        lesson_date = today if params.date == "today" else date.fromisoformat(params.date)
        # log_lesson records a past or today lesson. Future dates are rejected (the
        # model must not log something that hasn't happened) and dates older than 30
        # days are rejected (too stale to be a reliable record). Fail loudly with the
        # current date so the model can correct or ask Daria to resend.
        if lesson_date > today:
            raise ToolValidationError(
                self.name,
                f"date {lesson_date.isoformat()} is in the future; today is "
                f"{today.isoformat()}. log_lesson records a past or today lesson — "
                f"pass a date <= today.",
            )
        if (today - lesson_date).days > 30:
            raise ToolValidationError(
                self.name,
                f"date {lesson_date.isoformat()} is more than 30 days ago; today is "
                f"{today.isoformat()}. log_lesson only accepts dates within the last "
                f"30 days.",
            )

        # Idempotency: if this exact key was processed before, return the stored result.
        if idempotency_key is not None:
            prior = await ctx.audit.get_by_idempotency_key(idempotency_key)
            if prior is not None:
                return dict(prior.payload)  # type: ignore[arg-type]

        # Find or create a session for this date. Prefer an existing session (e.g. an email
        # booking); if none, create a manual completed session.
        existing = await ctx.sessions.get_by_date(lesson_date)
        if existing:
            session_model = existing[0]
        else:
            session_model = await ctx.sessions.create(
                date=lesson_date, status="completed", source="manual"
            )

        # DRIVE-8: attaching notes to a session still marked `scheduled` means the
        # lesson has actually happened (log_lesson only accepts today or a past date,
        # validated above). Mark it completed so pace() stops counting a finished
        # lesson as "1 lesson remaining" against the exam date. set_status mutates
        # the identity-mapped instance, so `session_model` reflects the new status.
        if session_model.status == "scheduled":
            await ctx.sessions.set_status(session_model.id, "completed")

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
            "session_status": session_model.status,
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


# --- DRIVE-5 manual lesson management (write_auto, audit-logged, idempotent) ---


def _validate_iso_date(value: str) -> str:
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("date must be ISO YYYY-MM-DD") from exc
    return value


def _validate_hhmm(value: str) -> str:
    if len(value) != 5 or value[2] != ":":
        raise ValueError("time must be HH:MM")
    hh, mm = value[:2], value[3:]
    if not (hh.isdigit() and mm.isdigit()) or not (0 <= int(hh) <= 23 and 0 <= int(mm) <= 59):
        raise ValueError("time must be HH:MM with valid hour/minute")
    return value


class AddLessonParams(ToolParams):
    date: str = Field(description="Lesson date, ISO YYYY-MM-DD.")
    start_time: str = Field(description="Lesson start time, HH:MM (24h).")
    end_time: str | None = Field(default=None, description="Optional end time, HH:MM (24h).")
    instructor: str | None = Field(default=None, description="Optional instructor name.")
    lesson_type: LessonType = Field(
        default=LessonType.RIJLES,
        description=(
            "Kind of lesson: rijles (a normal lesson, the default), "
            "proefles (a trial/mock lesson — when Daria says 'trial lesson', "
            "'mock lesson', 'proefles'), or exam (the real CBR practical exam — "
            "when Daria says 'exam', 'examen')."
        ),
    )

    @field_validator("date")
    @classmethod
    def _check_date(cls, value: str) -> str:
        return _validate_iso_date(value)

    @field_validator("start_time")
    @classmethod
    def _check_start(cls, value: str) -> str:
        return _validate_hhmm(value)

    @field_validator("end_time")
    @classmethod
    def _check_end(cls, value: str | None) -> str | None:
        return _validate_hhmm(value) if value is not None else None


class CancelLessonParams(ToolParams):
    date: str | None = Field(default=None, description="ISO YYYY-MM-DD of the lesson to cancel.")
    session_id: int | None = Field(default=None, description="Session id of the lesson to cancel.")

    @field_validator("date")
    @classmethod
    def _check_date(cls, value: str | None) -> str | None:
        return _validate_iso_date(value) if value is not None else None

    @model_validator(mode="after")
    def _exactly_one(self) -> CancelLessonParams:
        if (self.date is None) == (self.session_id is None):
            raise ValueError("provide exactly one of date or session_id")
        return self


class AddLessonTool:
    name = "add_lesson"
    description = (
        "Record a driving lesson Daria has booked (e.g. in your driving school's booking "
        "app) so it is tracked here. Auto-approved write. Pass the date (ISO YYYY-MM-DD, "
        "today or future only), start_time (HH:MM), optional end_time (HH:MM), optional "
        "instructor, and optional lesson_type (rijles — a normal lesson, the default; "
        "proefles — a trial/mock lesson; exam — the real CBR practical exam). "
        "Idempotent: re-adding the same lesson returns the existing scheduled "
        "session without creating a duplicate. This only records a booking Daria already "
        "made — it cannot book via the booking app."
    )
    tier = RiskTier.WRITE_AUTO

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": AddLessonParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = AddLessonParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc

        today = ctx.today()
        lesson_date = date.fromisoformat(params.date)
        # add_lesson records a scheduled (today or future) lesson. A past date is a
        # sign the model guessed the year or mishandled a relative date; reject it
        # loudly with the current date so the model corrects or asks Daria to resend.
        if lesson_date < today:
            raise ToolValidationError(
                self.name,
                f"date {params.date} is in the past; today is {today.isoformat()}. "
                f"add_lesson records a scheduled lesson — pass a date >= today.",
            )

        if idempotency_key is not None:
            prior = await ctx.audit.get_by_idempotency_key(idempotency_key)
            if prior is not None:
                return dict(prior.payload)  # type: ignore[arg-type]

        # Idempotency across days too: if a scheduled session already exists on this
        # date at this start_time, return it instead of creating a duplicate.
        existing_on_day = await ctx.sessions.get_by_date(lesson_date)
        for s in existing_on_day:
            if s.status == "scheduled" and s.start_time == params.start_time:
                result = _serialize_session(s)
                result["tool"] = self.name
                result["created"] = False
                result["deduplicated"] = True
                await ctx.audit.create(
                    action=self.name,
                    payload=result,
                    idempotency_key=idempotency_key,
                )
                return result

        session_model = await ctx.sessions.create(
            date=lesson_date,
            start_time=params.start_time,
            end_time=params.end_time,
            instructor=params.instructor,
            lesson_type=params.lesson_type.value,
            status="scheduled",
            source="manual",
        )
        result: dict[str, Any] = _serialize_session(session_model)
        result["tool"] = self.name
        result["created"] = True
        result["deduplicated"] = False
        await ctx.audit.create(
            action=self.name,
            payload=result,
            idempotency_key=idempotency_key,
        )
        return result


class CancelLessonTool:
    name = "cancel_lesson"
    description = (
        "Cancel a scheduled driving lesson recorded here. Auto-approved write. Pass "
        "either the session_id, or the date (ISO YYYY-MM-DD) to cancel scheduled "
        "lessons on that date. Idempotent: cancelling an already-cancelled or missing "
        "lesson is a no-op that reports the current state. This only cancels the record "
        "here — it cannot cancel a booking in the booking app."
    )
    tier = RiskTier.WRITE_AUTO

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": CancelLessonParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = CancelLessonParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc

        if idempotency_key is not None:
            prior = await ctx.audit.get_by_idempotency_key(idempotency_key)
            if prior is not None:
                return dict(prior.payload)  # type: ignore[arg-type]

        target: SessionModel | None
        if params.session_id is not None:
            target = await ctx.sessions.get_by_id(params.session_id)
        else:
            # date path: cancel all scheduled lessons on that date (usually one).
            day = date.fromisoformat(params.date)  # type: ignore[arg-type]
            day_sessions = await ctx.sessions.get_by_date(day)
            scheduled = [s for s in day_sessions if s.status == "scheduled"]
            if not scheduled:
                target = None
            elif len(scheduled) == 1:
                target = scheduled[0]
            else:
                cancelled: list[dict[str, Any]] = []
                for s in scheduled:
                    await ctx.sessions.set_status(s.id, "cancelled")
                    cancelled.append(
                        {"id": s.id, "date": s.date.isoformat(), "start_time": s.start_time}
                    )
                result_multi: dict[str, Any] = {
                    "tool": self.name,
                    "cancelled": cancelled,
                    "count": len(cancelled),
                    "already_cancelled": 0,
                }
                await ctx.audit.create(
                    action=self.name,
                    payload=result_multi,
                    idempotency_key=idempotency_key,
                )
                return result_multi

        if target is None:
            result: dict[str, Any] = {
                "tool": self.name,
                "cancelled": [],
                "count": 0,
                "already_cancelled": 0,
                "not_found": True,
            }
        elif target.status == "cancelled":
            result = {
                "tool": self.name,
                "cancelled": [],
                "count": 0,
                "already_cancelled": 1,
                "session": _serialize_session(target),
            }
        else:
            await ctx.sessions.set_status(target.id, "cancelled")
            result = {
                "tool": self.name,
                "cancelled": [
                    {
                        "id": target.id,
                        "date": target.date.isoformat(),
                        "start_time": target.start_time,
                    }
                ],
                "count": 1,
                "already_cancelled": 0,
                "session": _serialize_session(target),
            }
        await ctx.audit.create(
            action=self.name,
            payload=result,
            idempotency_key=idempotency_key,
        )
        return result


# --- Phase 2 read tools (analytics) ---


class GetSkillProgressParams(ToolParams):
    category: SkillCategory | None = Field(
        default=None,
        description="Optional filter: one of the seven CBR categories.",
    )


class GetSkillProgressTool:
    name = "get_skill_progress"
    description = (
        "Per-skill progress for Daria, derived from her logged assessments "
        "(good|ok|needs_attention). Returns each skill's status "
        "(not_started|weak|solid|in_progress), last note, last practiced date, "
        "and a stale flag (solid but not practised in 21+ days). "
        "Optionally filter by one of the seven CBR categories."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetSkillProgressParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetSkillProgressParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        all_skills = await ctx.skills.all()
        if params.category is not None:
            all_skills = [s for s in all_skills if s.category == params.category.value]
        skill_by_id = {s.id: s for s in all_skills}
        notes = await ctx.notes.all_with_session_dates()
        today = ctx.today()
        # Group assessments per skill, ordered chronologically (already ordered).
        by_skill: dict[int, list[NoteWithContext]] = {}
        for n in notes:
            if n.skill_id is not None and n.skill_id in skill_by_id:
                by_skill.setdefault(n.skill_id, []).append(n)

        out: list[dict[str, Any]] = []
        for skill in all_skills:
            skill_notes = by_skill.get(skill.id, [])
            assessments = [n.assessment for n in skill_notes if n.assessment]
            status = skill_status(assessments)
            last = skill_notes[-1] if skill_notes else None
            last_practiced = last.session_date if last else None
            out.append(
                {
                    "id": skill.id,
                    "name": skill.name,
                    "name_nl": skill.name_nl,
                    "category": skill.category,
                    "exam_relevant": skill.exam_relevant,
                    "status": status.value,
                    "last_note": last.note if last else None,
                    "last_note_assessment": last.assessment if last else None,
                    "last_practiced": last_practiced.isoformat() if last_practiced else None,
                    "stale": is_stale(status, last_practiced, today),
                }
            )
        return {
            "tool": self.name,
            "category": params.category.value if params.category else None,
            "count": len(out),
            "skills": out,
        }


class GetGapAnalysisTool:
    name = "get_gap_analysis"
    description = (
        "The star tool: Daria's weak and not-started skills ranked by exam weight, "
        "plus the pace verdict (lessons remaining vs skills not yet solid). "
        "status definitions: weak = latest assessment needs_attention; "
        "solid = last two assessments good; not_started = no notes; "
        "in_progress = otherwise. Use this for 'how am I doing?' and 'what should I focus on?'."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        all_skills = await ctx.skills.all()
        notes = await ctx.notes.all_with_session_dates()
        today = ctx.today()
        by_skill: dict[int, list[NoteWithContext]] = {}
        for n in notes:
            if n.skill_id is not None:
                by_skill.setdefault(n.skill_id, []).append(n)

        statuses: list[dict[str, Any]] = []
        for skill in all_skills:
            skill_notes = by_skill.get(skill.id, [])
            assessments = [n.assessment for n in skill_notes if n.assessment]
            status = skill_status(assessments)
            last = skill_notes[-1] if skill_notes else None
            statuses.append(
                {
                    "id": skill.id,
                    "name": skill.name,
                    "name_nl": skill.name_nl,
                    "category": skill.category,
                    "exam_relevant": skill.exam_relevant,
                    "status": status.value,
                    "last_practiced": last.session_date.isoformat() if last else None,
                }
            )

        def _rank_key(s: dict[str, Any]) -> tuple[int, int, int]:
            # exam-relevant first, then weak before not_started, then by id (stable).
            exam = 0 if s["exam_relevant"] else 1
            severity = 0 if s["status"] == SkillStatus.WEAK.value else 1
            return (exam, severity, int(s["id"]))

        weak = [s for s in statuses if s["status"] == SkillStatus.WEAK.value]
        not_started = [s for s in statuses if s["status"] == SkillStatus.NOT_STARTED.value]
        weak.sort(key=_rank_key)
        not_started.sort(key=_rank_key)

        total_exam_relevant = sum(1 for s in all_skills if s.exam_relevant)
        solid_count = sum(1 for s in statuses if s["status"] == SkillStatus.SOLID.value)
        until = ctx.exam_date
        lessons_left = await ctx.sessions.count_scheduled_from(today, until)
        pace_result = pace(
            lessons_left=lessons_left,
            solid_count=solid_count,
            total_exam_relevant=total_exam_relevant,
            exam_date=ctx.exam_date,
        )
        return {
            "tool": self.name,
            "weak": weak,
            "not_started": not_started,
            "pace": {
                "lessons_left": pace_result.lessons_left,
                "weak_or_missing_count": pace_result.weak_or_missing_count,
                "on_track": pace_result.on_track,
                "verdict": pace_result.verdict,
                "exam_date": ctx.exam_date.isoformat() if ctx.exam_date else None,
            },
        }


class GetNotesParams(ToolParams):
    skill: str | None = Field(
        default=None,
        description="Optional skill name to filter by (English or Dutch; fuzzy-matched).",
    )
    query: str | None = Field(
        default=None, description="Optional substring to search within note text."
    )


class GetNotesTool:
    name = "get_notes"
    description = (
        "Daria's own lesson notes, with their session dates. Optionally filter by a "
        "skill name (English or Dutch, fuzzy-matched to the skills list) and/or by a "
        "substring query on the note text. Use for 'what did I write about highways?' "
        "and 'how did my spiegels go?'."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetNotesParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetNotesParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        all_skills = await ctx.skills.all()
        skill_id: int | None = None
        unmatched_skill: str | None = None
        if params.skill is not None:
            matched = fuzzy_match_skill(params.skill, all_skills)
            if matched is None:
                unmatched_skill = params.skill
            else:
                skill_id = matched.id
        notes = await ctx.notes.all_with_session_dates()
        out: list[dict[str, Any]] = []
        query = params.query.lower() if params.query else None
        for n in notes:
            if skill_id is not None and n.skill_id != skill_id:
                continue
            if unmatched_skill is not None:
                continue
            if query is not None and query not in n.note.lower():
                continue
            out.append(
                {
                    "id": n.note_id,
                    "session_id": n.session_id,
                    "date": n.session_date.isoformat(),
                    "skill": n.skill_name,
                    "skill_name_nl": n.skill_name_nl,
                    "category": n.category,
                    "assessment": n.assessment,
                    "note": n.note,
                    "created_at": n.created_at_iso,
                }
            )
        return {
            "tool": self.name,
            "count": len(out),
            "notes": out,
            "unmatched_skill": unmatched_skill,
        }


class GetPaceTool:
    name = "get_pace"
    description = (
        "The pace verdict: lessons remaining before the exam date versus the number of "
        "skills not yet solid. Returns a `verdict` string — `no_exam_date` (no exam date "
        "is set; on_track is undefined, but the counts are still reported), `on_track`, "
        "or `off_track` — plus lessons_left, weak_or_missing_count, on_track (null when "
        "no exam date), and the exam_date."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        all_skills = await ctx.skills.all()
        notes = await ctx.notes.all_with_session_dates()
        today = ctx.today()
        by_skill: dict[int, list[NoteWithContext]] = {}
        for n in notes:
            if n.skill_id is not None:
                by_skill.setdefault(n.skill_id, []).append(n)
        solid_count = 0
        for skill in all_skills:
            skill_notes = by_skill.get(skill.id, [])
            assessments = [n.assessment for n in skill_notes if n.assessment]
            if skill_status(assessments) == SkillStatus.SOLID:
                solid_count += 1
        total_exam_relevant = sum(1 for s in all_skills if s.exam_relevant)
        until = ctx.exam_date
        lessons_left = await ctx.sessions.count_scheduled_from(today, until)
        pace_result = pace(
            lessons_left=lessons_left,
            solid_count=solid_count,
            total_exam_relevant=total_exam_relevant,
            exam_date=ctx.exam_date,
        )
        return {
            "tool": self.name,
            "lessons_left": pace_result.lessons_left,
            "weak_or_missing_count": pace_result.weak_or_missing_count,
            "on_track": pace_result.on_track,
            "verdict": pace_result.verdict,
            "exam_date": ctx.exam_date.isoformat() if ctx.exam_date else None,
        }


# --- Phase 2 docs tools ---


class GetCbrInfoParams(ToolParams):
    topic: CbrTopic = Field(
        description=(
            "Which CBR topic to retrieve: exam_structure, bijzondere_verrichtingen, "
            "assessment_criteria, self_reflection."
        )
    )


class GetCbrInfoTool:
    name = "get_cbr_info"
    description = (
        "Seeded CBR exam knowledge (from the knowledge base, sourced from cbr.nl). "
        "Returns the full content for one of: exam_structure, bijzondere_verrichtingen, "
        "assessment_criteria, self_reflection. Cite as 'Rijprocedure B, §…'."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetCbrInfoParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetCbrInfoParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        result = ctx.knowledge.get_topic(params.topic.value)
        result["tool"] = self.name
        return result


class GetTocTool:
    name = "get_toc"
    description = (
        "Return the full section tree of the CBR Rijprocedure B (the official "
        "driving-exam procedure): section ids, real section numbers, and titles in "
        "English and Dutch, in document order. Use this first to navigate the document, "
        "then call get_section with a chosen id. Cite sections by their real number."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": {}},
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        result = ctx.knowledge.get_toc()
        result["tool"] = self.name
        return result


class GetSectionParams(ToolParams):
    section_id: str = Field(
        description="Section id from get_toc() (e.g. 's183'). Returns verbatim en + nl text."
    )


class GetSectionTool:
    name = "get_section"
    description = (
        "Return one Rijprocedure B section's verbatim English and Dutch text plus its "
        "real section number. Call get_toc() first to obtain section ids. "
        "Cite the answer as 'Rijprocedure B, §<number>' (or the heading path if unnumbered)."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": GetSectionParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = GetSectionParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        result = ctx.knowledge.get_section(params.section_id)
        result["tool"] = self.name
        return result


class CbrSearchParams(ToolParams):
    query: str = Field(description="Free-text query to search the CBR knowledge base.")


class CbrSearchTool:
    name = "cbr_search"
    description = (
        "Keyword/heading search over the local CBR knowledge base "
        "(Rijprocedure B + seeded pages). Returns matching sections with heading and "
        "source. Cite as 'Rijprocedure B, §…'. This is the primary docs source; "
        "only fall back to web_search_cbr when this returns nothing."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": CbrSearchParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = CbrSearchParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        matches = ctx.knowledge.search(params.query)
        return {
            "tool": self.name,
            "query": params.query,
            "source_type": "kb",
            "count": len(matches),
            "matches": [
                {
                    "file": m.file,
                    "heading": m.heading,
                    "source": m.source,
                    "snippet": m.snippet,
                }
                for m in matches
            ],
        }


class WebSearchCbrParams(ToolParams):
    query: str = Field(
        description=(
            "Query to search live on cbr.nl. FALLBACK ONLY — call cbr_search first; "
            "use this only when cbr_search returns nothing (fees, waiting times, "
            "anything that changes)."
        )
    )


class WebSearchCbrTool:
    name = "web_search_cbr"
    description = (
        "Live search scoped to cbr.nl via Tavily. FALLBACK ONLY when cbr_search returns "
        "nothing (things that change: fees, waiting times). Untrusted content: this flow "
        "has no write tools. Prefix the answer with 'from cbr.nl just now:'."
    )
    tier = RiskTier.READ

    def openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": WebSearchCbrParams.model_json_schema(),
            },
        }

    async def run(
        self, arguments: dict[str, Any], ctx: ToolContext, idempotency_key: str | None
    ) -> dict[str, Any]:
        try:
            params = WebSearchCbrParams.model_validate(arguments)
        except ValidationError as exc:
            raise ToolValidationError(self.name, str(exc)) from exc
        outcome = await ctx.web.search(params.query)
        return serialize_web_results(outcome)


def phase2_tools() -> list[Tool]:
    """The full Phase 2 tool registry: all read tools + write tools + docs stack."""
    return [
        GetNextLessonsTool(),
        GetLessonHistoryTool(),
        GetNotesTool(),
        GetPaceTool(),
        GetSkillProgressTool(),
        GetGapAnalysisTool(),
        GetCbrInfoTool(),
        GetTocTool(),
        GetSectionTool(),
        CbrSearchTool(),
        WebSearchCbrTool(),
        LogLessonTool(),
        AddLessonTool(),
        CancelLessonTool(),
    ]


_READ_TOOLS: frozenset[str] = frozenset(
    {
        "get_next_lessons",
        "get_lesson_history",
        "get_notes",
        "get_pace",
        "get_skill_progress",
        "get_gap_analysis",
    }
)
_DOCS_TOOLS: frozenset[str] = frozenset(
    {"get_cbr_info", "get_toc", "get_section", "cbr_search", "web_search_cbr"}
)
_WRITE_TOOLS: frozenset[str] = frozenset({"log_lesson", "add_lesson", "cancel_lesson"})


def tools_for_label(label: str, all_tools: list[Tool]) -> list[Tool]:
    """Select the tool subset a router label is allowed to call.

    The router's coarse job is path safety (write vs read vs docs vs no-tools),
    not fine-grained dispatch (spec section 6b). Docs get no write tools and no DB
    read tools — that flow is CBR knowledge only.
    """
    by_name = {t.name: t for t in all_tools}
    if label == "log":
        return [by_name[n] for n in (_READ_TOOLS | _WRITE_TOOLS) if n in by_name]
    if label in ("lookup", "analytics"):
        return [by_name[n] for n in _READ_TOOLS if n in by_name]
    if label == "docs":
        return [by_name[n] for n in _DOCS_TOOLS if n in by_name]
    # smalltalk / other -> no tools (freeform path).
    return []


def tool_by_name(tools: list[Tool], name: str) -> Tool | None:
    for tool in tools:
        if tool.name == name:
            return tool
    return None


def dump_tool_result(result: dict[str, Any]) -> str:
    """Compact JSON for the message history / guardrail containment check."""
    return json.dumps(result, default=str, ensure_ascii=False)
