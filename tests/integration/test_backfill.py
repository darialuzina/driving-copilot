from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.backfill import load_backfill

BACKFILL = Path("fixtures/backfill.yaml")


async def test_backfill_loads_sessions_and_notes(session: AsyncSession) -> None:
    first = await load_backfill(session, BACKFILL)
    assert first["sessions_loaded"] == 6
    assert first["notes_loaded"] == 9


async def test_backfill_is_idempotent(session: AsyncSession) -> None:
    await load_backfill(session, BACKFILL)
    second = await load_backfill(session, BACKFILL)
    assert second["sessions_loaded"] == 0
    assert second["notes_loaded"] == 0
