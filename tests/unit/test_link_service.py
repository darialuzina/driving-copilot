from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.domain.errors import (
    LinkDisabledError,
    LinkExpiredError,
    LinkNotFoundError,
    ShortCodeTakenError,
)
from app.domain.link import Link, LinkStatus
from app.domain.value_objects import ShortCode, TargetUrl
from app.services.link_service import LinkService


class FakeLinkRepository:
    """In-memory репозиторий с теми же async-сигнатурами, что у LinkRepository."""

    def __init__(self) -> None:
        self._store: dict[str, Link] = {}
        self._next_id: int = 1

    async def add(self, link: Link) -> Link:
        stored = replace(link, id=self._next_id)
        self._store[stored.short_code.value] = stored
        self._next_id += 1
        return stored

    async def get_by_code(self, short_code: str) -> Link | None:
        return self._store.get(short_code)

    async def list_all(self, limit: int = 100) -> list[Link]:
        return list(self._store.values())[:limit]

    async def update(self, link: Link) -> Link:
        self._store[link.short_code.value] = link
        return link


def make_service(repo: FakeLinkRepository | None = None) -> LinkService:
    repo = repo or FakeLinkRepository()
    return LinkService(repository=repo, code_length=7)


# ---------------------------------------------------------------------------
# create_link
# ---------------------------------------------------------------------------


async def test_create_link_with_generated_code_returns_link() -> None:
    service = make_service()
    link = await service.create_link("https://example.com")

    assert link.id is not None
    assert link.short_code.value != ""
    assert link.target_url.value == "https://example.com"
    assert link.expires_at is None
    assert link.clicks == 0
    assert link.disabled is False


async def test_create_link_with_custom_code_uses_it() -> None:
    service = make_service()
    link = await service.create_link("https://example.com", custom_code="mycode")

    assert link.short_code.value == "mycode"


async def test_create_link_with_custom_code_taken_raises() -> None:
    repo = FakeLinkRepository()
    service = make_service(repo)

    await service.create_link("https://example.com", custom_code="mycode")

    with pytest.raises(ShortCodeTakenError, match="Short code already taken: mycode"):
        await service.create_link("https://other.com", custom_code="mycode")


async def test_create_link_with_ttl_sets_expires_at() -> None:
    service = make_service()
    link = await service.create_link("https://example.com", ttl_seconds=3600)

    assert link.expires_at is not None
    assert link.expires_at > link.created_at


async def test_create_link_with_ttl_zero_no_expiry() -> None:
    service = make_service()
    link = await service.create_link("https://example.com", ttl_seconds=0)

    assert link.expires_at is None


async def test_create_link_with_ttl_negative_no_expiry() -> None:
    service = make_service()
    link = await service.create_link("https://example.com", ttl_seconds=-10)

    assert link.expires_at is None


async def test_create_link_with_ttl_none_no_expiry() -> None:
    service = make_service()
    link = await service.create_link("https://example.com", ttl_seconds=None)

    assert link.expires_at is None


# ---------------------------------------------------------------------------
# get_link
# ---------------------------------------------------------------------------


async def test_get_link_existing_returns_link() -> None:
    service = make_service()
    await service.create_link("https://example.com", custom_code="abc123")

    found = await service.get_link("abc123")

    assert found.short_code.value == "abc123"
    assert found.target_url.value == "https://example.com"


async def test_get_link_not_found_raises() -> None:
    service = make_service()

    with pytest.raises(LinkNotFoundError, match="Link not found: missing"):
        await service.get_link("missing")


# ---------------------------------------------------------------------------
# list_links
# ---------------------------------------------------------------------------


async def test_list_links_returns_all() -> None:
    service = make_service()
    await service.create_link("https://a.com", custom_code="code1")
    await service.create_link("https://b.com", custom_code="code2")

    links = await service.list_links()

    assert len(links) == 2


async def test_list_links_respects_limit() -> None:
    service = make_service()
    await service.create_link("https://a.com", custom_code="code1")
    await service.create_link("https://b.com", custom_code="code2")
    await service.create_link("https://c.com", custom_code="code3")

    links = await service.list_links(limit=2)

    assert len(links) == 2


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------


async def test_resolve_active_link_increments_clicks() -> None:
    service = make_service()
    await service.create_link("https://example.com", custom_code="abc123")

    resolved = await service.resolve("abc123")

    assert resolved.clicks == 1


async def test_resolve_expired_link_raises() -> None:
    repo = FakeLinkRepository()
    service = make_service(repo)

    expired_link = Link(
        short_code=ShortCode("exp123"),
        target_url=TargetUrl("https://example.com"),
        created_at=datetime.now(UTC) - timedelta(hours=2),
        expires_at=datetime.now(UTC) - timedelta(hours=1),
    )
    await repo.add(expired_link)

    with pytest.raises(LinkExpiredError, match="Link expired: exp123"):
        await service.resolve("exp123")


async def test_resolve_disabled_link_raises() -> None:
    repo = FakeLinkRepository()
    service = make_service(repo)

    disabled_link = Link(
        short_code=ShortCode("dis123"),
        target_url=TargetUrl("https://example.com"),
        created_at=datetime.now(UTC),
        disabled=True,
    )
    await repo.add(disabled_link)

    with pytest.raises(LinkDisabledError, match="Link disabled: dis123"):
        await service.resolve("dis123")


async def test_resolve_not_found_raises() -> None:
    service = make_service()

    with pytest.raises(LinkNotFoundError, match="Link not found: missing"):
        await service.resolve("missing")


# ---------------------------------------------------------------------------
# disable_link
# ---------------------------------------------------------------------------


async def test_disable_link_sets_disabled() -> None:
    service = make_service()
    await service.create_link("https://example.com", custom_code="abc123")

    disabled = await service.disable_link("abc123")

    assert disabled.disabled is True
    assert disabled.status(datetime.now(UTC)) is LinkStatus.DISABLED


async def test_disable_link_not_found_raises() -> None:
    service = make_service()

    with pytest.raises(LinkNotFoundError, match="Link not found: missing"):
        await service.disable_link("missing")
