from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from typing import cast
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.db.models import LessonNoteModel
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.agent import AgentService
from app.services.knowledge import KnowledgeBase
from app.services.tools import (
    GetLessonHistoryTool,
    GetNextLessonsTool,
    LogLessonTool,
    ToolContext,
    phase2_tools,
)
from app.services.web_search import WebSearcher
from tests.conftest import FakeLlmClient, make_completion


@pytest.fixture
def ctx(session: AsyncSession, tmp_path: Path) -> ToolContext:
    return ToolContext(
        sessions=SessionRepository(session),
        skills=SkillRepository(session),
        notes=LessonNoteRepository(session),
        audit=AuditLogRepository(session),
        timezone=ZoneInfo("Europe/Amsterdam"),
        knowledge=KnowledgeBase(tmp_path / "knowledge"),
        web=WebSearcher(""),
    )


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        answer_model="answer",
        router_model="router",
        router_log_path=tmp_path / "router.jsonl",
    )


def _tool_call(call_id: str, name: str, arguments: dict[str, object]) -> dict[str, object]:
    return {"id": call_id, "name": name, "arguments": json.dumps(arguments)}


def _tool_result_payload(client: FakeLlmClient) -> dict[str, object]:
    message = client.completion_calls[1]["messages"][-1]
    return json.loads(cast(str, message["content"]))


# --- repository boundary ---


async def test_get_history_includes_today_completed_session(ctx: ToolContext) -> None:
    # DRIVE-9: history = date <= today. A same-day completed lesson is history.
    today = ctx.today()
    await ctx.sessions.create(date=today, start_time="15:00", status="completed", source="manual")
    await ctx.sessions.create(
        date=today - timedelta(days=2), status="completed", source="manual"
    )

    history = await ctx.sessions.get_history(today, limit=10)
    dates = [s.date for s in history]
    assert today in dates, "a same-day completed lesson must appear in lesson history"
    assert (today - timedelta(days=2)) in dates


async def test_get_history_excludes_future_sessions(ctx: ToolContext) -> None:
    today = ctx.today()
    await ctx.sessions.create(
        date=today + timedelta(days=3), start_time="10:00", status="scheduled", source="manual"
    )
    history = await ctx.sessions.get_history(today, limit=10)
    assert all(s.date <= today for s in history)


async def test_get_upcoming_includes_today_scheduled_until_completed(ctx: ToolContext) -> None:
    # DRIVE-9: upcoming = scheduled AND date >= today. A same-day scheduled lesson
    # stays in upcoming until log_lesson flips it to completed.
    today = ctx.today()
    session = await ctx.sessions.create(
        date=today, start_time="15:00", status="scheduled", source="email"
    )

    upcoming = await ctx.sessions.get_upcoming(today, days_ahead=14)
    ids = [s.id for s in upcoming]
    assert session.id in ids

    await ctx.sessions.set_status(session.id, "completed")
    upcoming = await ctx.sessions.get_upcoming(today, days_ahead=14)
    ids = [s.id for s in upcoming]
    assert session.id not in ids


# --- tool level ---


async def test_get_lesson_history_tool_returns_today_completed_with_notes(
    ctx: ToolContext,
) -> None:
    # The golden bug case: log a lesson today, then ask get_lesson_history. Before
    # DRIVE-9 the same-day completed session was filtered out (date < today), so
    # "what are my notes from today?" answered "no lesson recorded" while gap
    # analysis saw the same day's notes.
    await LogLessonTool().run(
        {
            "date": "today",
            "skills": [{"skill": "parking", "assessment": "good", "note": "parallel parking ok"}],
        },
        ctx,
        idempotency_key="log:today-history",
    )

    result = await GetLessonHistoryTool().run({}, ctx, idempotency_key=None)
    sessions = cast(list[dict[str, object]], result["sessions"])
    today_iso = ctx.today().isoformat()
    todays = [s for s in sessions if s["date"] == today_iso]
    assert len(todays) == 1, "today's completed lesson must be in get_lesson_history"
    notes = cast(list[dict[str, object]], todays[0]["notes"])
    assert len(notes) == 1
    assert "parking" in cast(str, notes[0]["skill"])


async def test_get_next_lessons_excludes_today_completed_session(ctx: ToolContext) -> None:
    # A same-day completed lesson must not also appear in upcoming (no double count).
    today = ctx.today()
    await ctx.sessions.create(
        date=today, start_time="15:00", status="completed", source="manual"
    )
    result = await GetNextLessonsTool().run({}, ctx, idempotency_key=None)
    sessions = cast(list[dict[str, object]], result["sessions"])
    assert all(s["date"] != today.isoformat() for s in sessions)


# --- golden end-to-end: "what are my notes from today?" over a same-day completed session ---


async def test_golden_what_are_my_notes_from_today_over_same_day_completed(
    session: AsyncSession, ctx: ToolContext, settings: Settings
) -> None:
    # Daria logs today's lesson, then asks "what are my notes from today?". The
    # lookup path must call get_lesson_history and the today session + its notes
    # must come back (regression for the date < today exclusion).
    await LogLessonTool().run(
        {
            "date": "today",
            "skills": [{"skill": "parking", "assessment": "good", "note": "parallel parking ok"}],
        },
        ctx,
        idempotency_key="log:golden-today",
    )

    today_iso = ctx.today().isoformat()
    client = FakeLlmClient(
        completions=[
            make_completion(calls=[_tool_call("c1", "get_lesson_history", {"limit": 10})]),
            make_completion(
                content=f"On {today_iso} you practiced parking (good): parallel parking ok."
            ),
        ]
    )
    agent = AgentService(client, settings)
    reply = await agent.handle(
        "what are my notes from today?", "lookup", phase2_tools(), ctx
    )

    assert today_iso in reply, "the reply must cite today's date"
    assert "parking" in reply.lower()

    # The tool result the model saw must contain today's session with its note —
    # this is the exact data the old date < today filter dropped.
    payload = _tool_result_payload(client)
    sessions = cast(list[dict[str, object]], payload["sessions"])
    todays = [s for s in sessions if s["date"] == today_iso]
    assert len(todays) == 1
    notes = cast(list[dict[str, object]], todays[0]["notes"])
    assert len(notes) == 1
    assert "parking" in cast(str, notes[0]["skill"]).lower()

    # The note row is real and linked to today's session.
    db_notes = (await session.execute(select(LessonNoteModel))).scalars().all()
    assert len(db_notes) == 1
