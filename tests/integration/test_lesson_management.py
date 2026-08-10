from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogModel, SessionModel
from app.repositories.audit_log_repository import AuditLogRepository
from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.knowledge import KnowledgeBase
from app.services.tools import (
    AddLessonTool,
    CancelLessonTool,
    GetNextLessonsTool,
    ToolContext,
)
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


def _future_iso(ctx: ToolContext, days: int = 3) -> str:
    return (ctx.today() + timedelta(days=days)).isoformat()


# --- add_lesson ---


async def test_add_lesson_creates_scheduled_session_picked_up_by_get_next_lessons(
    ctx: ToolContext,
) -> None:
    lesson_date = _future_iso(ctx, 3)
    result = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "15:00", "instructor": "Marco"},
        ctx,
        idempotency_key="add:1",
    )
    assert result["created"] is True
    assert result["deduplicated"] is False
    assert result["status"] == "scheduled"
    assert result["source"] == "manual"
    assert result["instructor"] == "Marco"
    assert result["start_time"] == "15:00"
    assert result["id"] is not None

    # get_next_lessons picks it up automatically.
    upcoming = await GetNextLessonsTool().run({}, ctx, idempotency_key=None)
    dates = [s["date"] for s in upcoming["sessions"]]
    assert lesson_date in dates


async def test_add_lesson_writes_audit_log(ctx: ToolContext) -> None:
    lesson_date = _future_iso(ctx, 4)
    await AddLessonTool().run(
        {"date": lesson_date, "start_time": "10:00"}, ctx, idempotency_key="add:audit"
    )
    audit = await ctx.audit.get_by_idempotency_key("add:audit")
    assert audit is not None
    assert audit.action == "add_lesson"


async def test_add_lesson_idempotent_same_key_returns_stored_no_duplicate(
    session: AsyncSession, ctx: ToolContext
) -> None:
    lesson_date = _future_iso(ctx, 5)
    args = {"date": lesson_date, "start_time": "11:00", "instructor": "Sandra"}
    first = await AddLessonTool().run(args, ctx, idempotency_key="add:dup")
    await session.commit()
    second = await AddLessonTool().run(args, ctx, idempotency_key="add:dup")
    assert first["id"] == second["id"]
    rows = (
        (
            await session.execute(
                select(SessionModel).where(SessionModel.date == date.fromisoformat(lesson_date))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_add_lesson_dedup_same_date_and_start_time_no_duplicate(
    session: AsyncSession, ctx: ToolContext
) -> None:
    lesson_date = _future_iso(ctx, 6)
    # First call with an idempotency key.
    first = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "13:00", "instructor": "Marco"},
        ctx,
        idempotency_key="add:a",
    )
    await session.commit()
    # Second call with a DIFFERENT idempotency key but same date+start_time: must
    # return the existing session, not create a duplicate.
    second = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "13:00", "instructor": "Marco"},
        ctx,
        idempotency_key="add:b",
    )
    assert second["created"] is False
    assert second["deduplicated"] is True
    assert second["id"] == first["id"]
    rows = (
        (
            await session.execute(
                select(SessionModel).where(SessionModel.date == date.fromisoformat(lesson_date))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 1


async def test_add_lesson_two_distinct_lessons_same_day_create_both(
    session: AsyncSession, ctx: ToolContext
) -> None:
    lesson_date = _future_iso(ctx, 7)
    await AddLessonTool().run(
        {"date": lesson_date, "start_time": "09:00"}, ctx, idempotency_key="add:am"
    )
    await AddLessonTool().run(
        {"date": lesson_date, "start_time": "14:00"}, ctx, idempotency_key="add:pm"
    )
    await session.commit()
    rows = (
        (
            await session.execute(
                select(SessionModel).where(SessionModel.date == date.fromisoformat(lesson_date))
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) == 2


async def test_add_lesson_rejects_bad_params(ctx: ToolContext) -> None:
    from app.domain.errors import ToolValidationError

    with pytest.raises(ToolValidationError):
        await AddLessonTool().run(
            {"date": "Aug 12", "start_time": "15:00"}, ctx, idempotency_key=None
        )


async def test_add_lesson_rejects_past_date(ctx: ToolContext) -> None:
    # DRIVE-5b: a past date for a *scheduled* lesson means the model guessed the year
    # or mishandled a relative date. Fail loudly with today's date so it can correct.
    from app.domain.errors import ToolValidationError

    past = (ctx.today() - timedelta(days=1)).isoformat()
    with pytest.raises(ToolValidationError) as exc_info:
        await AddLessonTool().run(
            {"date": past, "start_time": "15:00"}, ctx, idempotency_key=None
        )
    assert "past" in exc_info.value.reason
    assert ctx.today().isoformat() in exc_info.value.reason


async def test_add_lesson_accepts_today_date(ctx: ToolContext) -> None:
    today_iso = ctx.today().isoformat()
    result = await AddLessonTool().run(
        {"date": today_iso, "start_time": "15:00"}, ctx, idempotency_key="add:today"
    )
    assert result["created"] is True
    assert result["date"] == today_iso


# --- cancel_lesson ---


async def test_cancel_lesson_by_session_id_cancels(ctx: ToolContext) -> None:
    lesson_date = _future_iso(ctx, 8)
    added = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "16:00"}, ctx, idempotency_key="add:c1"
    )
    result = await CancelLessonTool().run(
        {"session_id": added["id"]}, ctx, idempotency_key="cancel:sid"
    )
    assert result["count"] == 1
    assert result["cancelled"][0]["id"] == added["id"]
    assert result["session"]["status"] == "cancelled"

    # The lesson is no longer returned by get_next_lessons (which filters scheduled).
    upcoming = await GetNextLessonsTool().run({}, ctx, idempotency_key=None)
    ids = [s["id"] for s in upcoming["sessions"]]
    assert added["id"] not in ids


async def test_cancel_lesson_by_date_cancels(ctx: ToolContext) -> None:
    lesson_date = _future_iso(ctx, 9)
    await AddLessonTool().run(
        {"date": lesson_date, "start_time": "17:00"}, ctx, idempotency_key="add:d1"
    )
    result = await CancelLessonTool().run({"date": lesson_date}, ctx, idempotency_key="cancel:date")
    assert result["count"] == 1
    assert result["cancelled"][0]["date"] == lesson_date


async def test_cancel_lesson_already_cancelled_is_noop(ctx: ToolContext) -> None:
    lesson_date = _future_iso(ctx, 10)
    added = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "18:00"}, ctx, idempotency_key="add:e1"
    )
    first = await CancelLessonTool().run(
        {"session_id": added["id"]}, ctx, idempotency_key="cancel:e1"
    )
    assert first["count"] == 1
    # Re-cancel with a fresh key: idempotent no-op reporting already_cancelled.
    second = await CancelLessonTool().run(
        {"session_id": added["id"]}, ctx, idempotency_key="cancel:e2"
    )
    assert second["count"] == 0
    assert second["already_cancelled"] == 1
    assert second["session"]["status"] == "cancelled"


async def test_cancel_lesson_missing_session_reports_not_found(ctx: ToolContext) -> None:
    result = await CancelLessonTool().run(
        {"session_id": 99999}, ctx, idempotency_key="cancel:missing"
    )
    assert result["count"] == 0
    assert result["not_found"] is True


async def test_cancel_lesson_by_date_no_scheduled_reports_not_found(ctx: ToolContext) -> None:
    # A date with no scheduled lessons at all.
    far_future = (ctx.today() + timedelta(days=400)).isoformat()
    result = await CancelLessonTool().run({"date": far_future}, ctx, idempotency_key="cancel:empty")
    assert result["count"] == 0
    assert result["not_found"] is True


async def test_cancel_lesson_writes_audit_log(ctx: ToolContext) -> None:
    lesson_date = _future_iso(ctx, 11)
    added = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "19:00"}, ctx, idempotency_key="add:f1"
    )
    await CancelLessonTool().run({"session_id": added["id"]}, ctx, idempotency_key="cancel:f1")
    cancel_audit = await ctx.audit.get_by_idempotency_key("cancel:f1")
    assert cancel_audit is not None
    assert cancel_audit.action == "cancel_lesson"
    add_audit = await ctx.audit.get_by_idempotency_key("add:f1")
    assert add_audit is not None
    assert add_audit.action == "add_lesson"


async def test_cancel_lesson_idempotent_same_key_returns_stored(
    session: AsyncSession, ctx: ToolContext
) -> None:
    lesson_date = _future_iso(ctx, 12)
    added = await AddLessonTool().run(
        {"date": lesson_date, "start_time": "08:00"}, ctx, idempotency_key="add:g1"
    )
    args = {"session_id": added["id"]}
    first = await CancelLessonTool().run(args, ctx, idempotency_key="cancel:g1")
    await session.commit()
    second = await CancelLessonTool().run(args, ctx, idempotency_key="cancel:g1")
    assert first == second


async def test_cancel_lesson_rejects_neither_or_both(ctx: ToolContext) -> None:
    from app.domain.errors import ToolValidationError

    with pytest.raises(ToolValidationError):
        await CancelLessonTool().run({}, ctx, idempotency_key=None)
    with pytest.raises(ToolValidationError):
        await CancelLessonTool().run(
            {"date": "2026-08-12", "session_id": 1}, ctx, idempotency_key=None
        )


# --- audit_log sanity: every write leaves exactly one row per idempotency key ---


async def test_add_then_cancel_each_write_one_audit_row(
    session: AsyncSession, ctx: ToolContext
) -> None:
    lesson_date = _future_iso(ctx, 13)
    await AddLessonTool().run(
        {"date": lesson_date, "start_time": "12:00"}, ctx, idempotency_key="audit:add"
    )
    sess = (
        (
            await session.execute(
                select(SessionModel).where(SessionModel.date == date.fromisoformat(lesson_date))
            )
        )
        .scalars()
        .first()
    )
    assert sess is not None
    await CancelLessonTool().run({"session_id": sess.id}, ctx, idempotency_key="audit:cancel")
    await session.commit()
    add_rows = (
        (
            await session.execute(
                select(AuditLogModel).where(AuditLogModel.idempotency_key == "audit:add")
            )
        )
        .scalars()
        .all()
    )
    cancel_rows = (
        (
            await session.execute(
                select(AuditLogModel).where(AuditLogModel.idempotency_key == "audit:cancel")
            )
        )
        .scalars()
        .all()
    )
    assert len(add_rows) == 1
    assert len(cancel_rows) == 1
