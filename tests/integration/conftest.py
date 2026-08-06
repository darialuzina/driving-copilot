from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

import app.db.session as session_mod
from app.db.base import Base
from app.db.models import SkillModel
from app.db.seed import SKILLS
from app.db.session import get_engine, get_sessionmaker


@pytest.fixture(autouse=True)
async def isolated_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None]:
    monkeypatch.setattr(session_mod, "_engine", None)
    engine = get_engine()
    await _create_tables(engine)
    await _truncate(engine)
    await _seed_skills(engine)
    yield
    await _truncate(engine)
    monkeypatch.setattr(session_mod, "_engine", None)


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    async with get_sessionmaker()() as s:
        yield s
        await s.rollback()


async def _create_tables(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def _seed_skills(engine: AsyncEngine) -> None:
    async with get_sessionmaker()() as session:
        for entry in SKILLS:
            session.add(
                SkillModel(
                    category=entry["category"],
                    name=entry["name"],
                    name_nl=entry["name_nl"],
                    exam_relevant=True,
                )
            )
        await session.commit()


async def _truncate(engine: AsyncEngine) -> None:
    async with get_sessionmaker()() as session:
        for table in ("audit_log", "lesson_notes", "sessions", "skills"):
            await session.execute(text(f"DELETE FROM {table}"))
        await session.commit()
