from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonNoteModel, SessionModel
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.knowledge import KnowledgeBase
from app.services.tools import AddLessonTool, LogLessonTool, ToolContext
from app.services.web_search import WebSearcher


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


async def test_log_lesson_creates_note_linked_to_parking_skill(
    session: AsyncSession, ctx: ToolContext
) -> None:
    tool = LogLessonTool()
    result = await tool.run(
        {
            "date": "today",
            "skills": [{"skill": "parking", "assessment": "good", "note": "did parking, all ok"}],
        },
        ctx,
        idempotency_key="log:test-1",
    )
    assert result["note_ids"], "a note should have been created"
    assert result["matched_skills"], "the skill should have matched"
    matched = result["matched_skills"][0]
    assert "parking" in matched["skill"]

    # The note is linked to a real skill row (skill_id is not None).
    note = await session.get(LessonNoteModel, result["note_ids"][0])
    assert note is not None
    assert note.skill_id is not None

    # A session was created for today.
    today = date.today()
    sessions = await SessionRepository(session).get_by_date(today)
    assert len(sessions) == 1
    assert sessions[0].source == "manual"

    # An audit row was written with the idempotency key.
    audit = await AuditLogRepository(session).get_by_idempotency_key("log:test-1")
    assert audit is not None
    assert audit.action == "log_lesson"


async def test_log_lesson_idempotent_same_key(session: AsyncSession, ctx: ToolContext) -> None:
    tool = LogLessonTool()
    args = {
        "date": "today",
        "skills": [{"skill": "roundabouts", "assessment": "ok", "note": "roundabout ok"}],
    }
    first = await tool.run(args, ctx, idempotency_key="log:dup")
    await session.commit()
    second = await tool.run(args, ctx, idempotency_key="log:dup")
    # Same result, no extra notes created.
    assert first["note_ids"] == second["note_ids"]
    notes = (await session.execute(select(LessonNoteModel))).scalars().all()
    assert len(notes) == 1


async def test_log_lesson_unmatched_skill_becomes_general_note(
    session: AsyncSession, ctx: ToolContext
) -> None:
    tool = LogLessonTool()
    result = await tool.run(
        {
            "date": "today",
            "skills": [{"skill": "quantum drifting", "assessment": "ok", "note": "n/a"}],
        },
        ctx,
        idempotency_key="log:unmatched",
    )
    assert result["unmatched_skills"] == ["quantum drifting"]
    note = await session.get(LessonNoteModel, result["note_ids"][0])
    assert note is not None
    assert note.skill_id is None  # stored as a general note


async def test_log_lesson_distinct_calls_distinct_keys(
    session: AsyncSession, ctx: ToolContext
) -> None:
    """Two genuinely different log calls on the same day must not collide."""
    from app.services.agent import make_write_idempotency_key

    today = "2026-08-10"
    k1 = make_write_idempotency_key(
        "log_lesson",
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "ok"}]},
        today,
    )
    k2 = make_write_idempotency_key(
        "log_lesson",
        {
            "date": "today",
            "skills": [{"skill": "roundabouts", "assessment": "needs_attention", "note": "bad"}],
        },
        today,
    )
    tool = LogLessonTool()
    await tool.run(
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "ok"}]},
        ctx,
        idempotency_key=k1,
    )
    await tool.run(
        {
            "date": "today",
            "skills": [{"skill": "roundabouts", "assessment": "needs_attention", "note": "bad"}]
        },
        ctx,
        idempotency_key=k2,
    )
    notes = (await session.execute(select(LessonNoteModel))).scalars().all()
    assert len(notes) == 2


# --- DRIVE-5b: date validation (code, fail loudly) ---


async def test_log_lesson_rejects_future_date(ctx: ToolContext) -> None:
    from app.domain.errors import ToolValidationError

    future = (ctx.today() + timedelta(days=1)).isoformat()
    with pytest.raises(ToolValidationError) as exc_info:
        await LogLessonTool().run(
            {"date": future, "skills": [{"skill": "parking", "assessment": "good", "note": "x"}]},
            ctx,
            idempotency_key=None,
        )
    assert "future" in exc_info.value.reason
    assert ctx.today().isoformat() in exc_info.value.reason


async def test_log_lesson_rejects_date_older_than_30_days(ctx: ToolContext) -> None:
    from app.domain.errors import ToolValidationError

    old = (ctx.today() - timedelta(days=31)).isoformat()
    with pytest.raises(ToolValidationError) as exc_info:
        await LogLessonTool().run(
            {"date": old, "skills": [{"skill": "parking", "assessment": "good", "note": "x"}]},
            ctx,
            idempotency_key=None,
        )
    assert "30 days" in exc_info.value.reason
    assert ctx.today().isoformat() in exc_info.value.reason


async def test_log_lesson_accepts_date_within_30_days(ctx: ToolContext) -> None:
    recent = (ctx.today() - timedelta(days=10)).isoformat()
    result = await LogLessonTool().run(
        {"date": recent, "skills": [{"skill": "parking", "assessment": "good", "note": "x"}]},
        ctx,
        idempotency_key="log:recent",
    )
    assert result["date"] == recent


# --- DRIVE-8: log_lesson completes a still-scheduled session dated today/earlier ---


async def test_log_lesson_marks_today_scheduled_session_completed(
    session: AsyncSession, ctx: ToolContext
) -> None:
    # A lesson booked for today (status=scheduled) that Daria then practices.
    today = ctx.today()
    await AddLessonTool().run(
        {"date": today.isoformat(), "start_time": "15:00"},
        ctx,
        idempotency_key="add:today-scheduled",
    )
    result = await LogLessonTool().run(
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "ok"}]},
        ctx,
        idempotency_key="log:today-scheduled",
    )
    # The transition is surfaced to the model and persisted.
    assert result["session_status"] == "completed"
    sessions = await SessionRepository(session).get_by_date(today)
    assert len(sessions) == 1
    assert sessions[0].status == "completed"


async def test_log_lesson_marks_past_scheduled_session_completed(
    session: AsyncSession, ctx: ToolContext
) -> None:
    # A scheduled session from a few days ago (e.g. an email booking never flipped
    # to completed) that Daria logs notes against now.
    past = ctx.today() - timedelta(days=3)
    await ctx.sessions.create(
        date=past, start_time="10:00", status="scheduled", source="email"
    )
    result = await LogLessonTool().run(
        {
            "date": past.isoformat(),
            "skills": [{"skill": "parking", "assessment": "ok", "note": "x"}],
        },
        ctx,
        idempotency_key="log:past-scheduled",
    )
    assert result["session_status"] == "completed"
    rows = (
        (await session.execute(select(SessionModel).where(SessionModel.date == past)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "completed"


async def test_log_lesson_new_session_is_completed_and_reports_status(ctx: ToolContext) -> None:
    # No prior session -> log_lesson creates a manual completed one; the result
    # surfaces that status (regression guard for the session_status field).
    result = await LogLessonTool().run(
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "x"}]},
        ctx,
        idempotency_key="log:new-status",
    )
    assert result["session_status"] == "completed"


async def test_log_lesson_does_not_touch_already_completed_session(
    session: AsyncSession, ctx: ToolContext
) -> None:
    # An already-completed session must stay completed (idempotent transition).
    today = ctx.today()
    await ctx.sessions.create(
        date=today, start_time="09:00", status="completed", source="manual"
    )
    result = await LogLessonTool().run(
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "x"}]},
        ctx,
        idempotency_key="log:already-done",
    )
    assert result["session_status"] == "completed"
    rows = (
        (await session.execute(select(SessionModel).where(SessionModel.date == today)))
        .scalars()
        .all()
    )
    assert len(rows) == 1
    assert rows[0].status == "completed"
