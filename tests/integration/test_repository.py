from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.domain.link import Link
from app.domain.value_objects import ShortCode, TargetUrl
from app.repositories.link_repository import LinkRepository


def _link(
    code: str = "code1",
    url: str = "https://example.com",
    *,
    clicks: int = 0,
    disabled: bool = False,
    expires_at: datetime | None = None,
    created_at: datetime | None = None,
) -> Link:
    return Link(
        short_code=ShortCode(code),
        target_url=TargetUrl(url),
        created_at=created_at or datetime.now(UTC),
        expires_at=expires_at,
        clicks=clicks,
        disabled=disabled,
    )


async def _repo(session: AsyncSession) -> LinkRepository:
    return LinkRepository(session)


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


async def test_add_assigns_id_and_persists() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        link = await repo.add(_link("add01", "https://a.com"))
        await session.commit()
    assert link.id is not None and link.id > 0
    assert link.short_code.value == "add01"
    assert link.target_url.value == "https://a.com"


async def test_add_preserves_expires_at_and_defaults() -> None:
    expires = datetime.now(UTC) + timedelta(hours=1)
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        link = await repo.add(_link("add02", expires_at=expires))
        await session.commit()
    assert link.expires_at == expires
    assert link.clicks == 0
    assert link.disabled is False


# ---------------------------------------------------------------------------
# get_by_code
# ---------------------------------------------------------------------------


async def test_get_by_code_empty_table_returns_none() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        assert await repo.get_by_code("abse") is None


async def test_get_by_code_first_row_match() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        await repo.add(_link("gg01", "https://a.com"))
        await repo.add(_link("gg02", "https://b.com"))
        await session.flush()
        found = await repo.get_by_code("gg01")
    assert found is not None
    assert found.short_code.value == "gg01"


async def test_get_by_code_later_row_match() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        await repo.add(_link("gg03", "https://a.com"))
        await repo.add(_link("gg04", "https://b.com"))
        await session.flush()
        found = await repo.get_by_code("gg04")
    assert found is not None
    assert found.short_code.value == "gg04"


async def test_get_by_code_no_match_returns_none() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        await repo.add(_link("gg05", "https://a.com"))
        await session.flush()
        assert await repo.get_by_code("miss") is None


# ---------------------------------------------------------------------------
# list_all
# ---------------------------------------------------------------------------


async def test_list_all_empty_returns_empty_list() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        assert await repo.list_all() == []


async def test_list_all_returns_all_within_default_limit() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        await repo.add(_link("ll01", "https://a.com"))
        await repo.add(_link("ll02", "https://b.com"))
        await repo.add(_link("ll03", "https://c.com"))
        await session.flush()
        result = await repo.list_all()
    assert len(result) == 3
    codes = {link.short_code.value for link in result}
    assert codes == {"ll01", "ll02", "ll03"}


async def test_list_all_respects_custom_limit() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        for i in range(5):
            await repo.add(_link(f"cc0{i}", f"https://x{i}.com"))
        await session.flush()
        result = await repo.list_all(limit=2)
    assert len(result) == 2


async def test_list_all_orders_by_id_desc() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        await repo.add(_link("oo01", "https://a.com"))
        await repo.add(_link("oo02", "https://b.com"))
        await repo.add(_link("oo03", "https://c.com"))
        await session.flush()
        result = await repo.list_all()
    assert result[0].short_code.value == "oo03"
    assert result[-1].short_code.value == "oo01"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


async def test_update_existing_row_persists_clicks_and_disabled() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        link = await repo.add(_link("uu01", "https://a.com"))
        await session.flush()
        updated = await repo.update(link.with_click().with_click().disable())
        await session.flush()
        refetched = await repo.get_by_code("uu01")
    assert updated.clicks == 2
    assert updated.disabled is True
    assert refetched is not None
    assert refetched.clicks == 2
    assert refetched.disabled is True


async def test_update_nonexistent_code_returns_link_unchanged() -> None:
    async with get_sessionmaker()() as session:
        repo = await _repo(session)
        ghost = _link("ghst", "https://a.com")
        result = await repo.update(ghost.with_click())
        await session.flush()
        assert result.clicks == 1
        assert await repo.get_by_code("ghst") is None
