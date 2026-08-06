from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

import app.db.session as session_mod
from app.config import Settings
from app.db.session import get_engine, get_sessionmaker, provide_session


def patch_engine(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> str:
    db_file = tmp_path / "ws_session.db"
    url = f"sqlite+aiosqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(session_mod, "_engine", None)
    monkeypatch.setattr(
        "app.db.session.get_settings",
        lambda: Settings(database_url=url),
    )
    return url


# ---------------------------------------------------------------------------
# get_engine
# ---------------------------------------------------------------------------


def test_get_engine_creates_then_caches(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_engine(monkeypatch, tmp_path)
    first = get_engine()
    second = get_engine()
    assert first is second


def test_get_engine_returns_cached_instance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_engine(monkeypatch, tmp_path)
    established = get_engine()
    assert get_engine() is established


# ---------------------------------------------------------------------------
# get_sessionmaker
# ---------------------------------------------------------------------------


async def test_get_sessionmaker_opens_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_engine(monkeypatch, tmp_path)
    maker = get_sessionmaker()
    async with maker() as session:
        assert session is not None


# ---------------------------------------------------------------------------
# provide_session: commit path
# ---------------------------------------------------------------------------


async def test_provide_session_commits_on_clean_exit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_engine(monkeypatch, tmp_path)
    gen = provide_session()
    session = await gen.asend(None)
    assert session is not None
    with pytest.raises(StopAsyncIteration):
        await gen.asend(None)


# ---------------------------------------------------------------------------
# provide_session: rollback path
# ---------------------------------------------------------------------------


async def test_provide_session_rolls_back_on_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    patch_engine(monkeypatch, tmp_path)
    gen: AsyncGenerator[AsyncSession] = provide_session()
    await gen.asend(None)
    with pytest.raises(RuntimeError, match="boom"):
        await gen.athrow(RuntimeError("boom"))
