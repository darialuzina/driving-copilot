from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

import app.db.session as session_mod
from app.db.base import Base
from app.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
async def isolated_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None]:
    monkeypatch.setattr(session_mod, "_engine", None)
    engine = get_engine()
    await _create_tables(engine)
    await _truncate(engine)
    yield
    await _truncate(engine)
    monkeypatch.setattr(session_mod, "_engine", None)


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _truncate(engine: AsyncEngine) -> None:
    async with get_sessionmaker()() as session:
        await session.execute(text("DELETE FROM links"))
        await session.commit()
