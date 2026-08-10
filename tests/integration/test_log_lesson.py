from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonNoteModel
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.tools import LogLessonTool, ToolContext


@pytest.fixture
def ctx(session: AsyncSession) -> ToolContext:
    return ToolContext(
        sessions=SessionRepository(session),
        skills=SkillRepository(session),
        notes=LessonNoteRepository(session),
        audit=AuditLogRepository(session),
        timezone=ZoneInfo("Europe/Amsterdam"),
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
