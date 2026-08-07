from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

import app.db.session as session_mod
from app.config import get_settings
from app.db.base import Base
from app.db.models import SkillModel
from app.db.seed import SKILLS

settings = get_settings()


# --- test engine (module-level singleton, always the test database) ---

_test_engine: AsyncEngine | None = None


def get_test_engine() -> AsyncEngine:
    global _test_engine
    if _test_engine is None:
        _test_engine = create_async_engine(settings.test_database_url, pool_pre_ping=True)
    return _test_engine


@pytest.fixture(autouse=True)
async def _test_db(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None]:  # pyright: ignore[reportUnusedFunction]
    """Route ALL DB access to the test database and ensure schema + seed data exist.

    Monkeypatches app.db.session so production code that calls get_engine /
    get_sessionmaker connects to the test database, never the dev database.
    """
    engine = get_test_engine()
    test_sm = async_sessionmaker(engine, expire_on_commit=False)

    # Redirect the app's session module to the test engine.
    monkeypatch.setattr(session_mod, "_engine", engine)
    monkeypatch.setattr(session_mod, "get_engine", lambda: engine)
    monkeypatch.setattr(session_mod, "get_sessionmaker", lambda: test_sm)

    # Create tables (idempotent — safe to call every test).
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed skills reference data if empty (persists in the test database).
    async with test_sm() as s:
        count = (await s.execute(text("SELECT COUNT(*) FROM skills"))).scalar_one()
        if count == 0:
            for entry in SKILLS:
                s.add(
                    SkillModel(
                        category=entry["category"],
                        name=entry["name"],
                        name_nl=entry["name_nl"],
                        exam_relevant=True,
                    )
                )
            await s.commit()

    yield


@pytest.fixture
async def session() -> AsyncGenerator[AsyncSession]:
    """Transactional test session: every test runs inside a transaction that rolls back.

    Uses a connection-bound session with join_transaction_mode="create_savepoint" so
    that session.commit() inside the code under test commits to a savepoint (not the
    outer transaction). At teardown the outer transaction is rolled back, undoing all
    test data. No truncation needed — nothing is permanently written.
    """
    engine = get_test_engine()
    async with engine.connect() as conn:
        await conn.begin()
        async with AsyncSession(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        ) as s:
            yield s
        await conn.rollback()
