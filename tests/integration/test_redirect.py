from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import ASGITransport, AsyncClient

from app.db.session import get_sessionmaker
from app.domain.link import Link
from app.domain.value_objects import ShortCode, TargetUrl
from app.main import app
from app.repositories.link_repository import LinkRepository


async def client() -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", follow_redirects=False
    )


async def _seed_link(link: Link) -> None:
    async with get_sessionmaker()() as session:
        repo = LinkRepository(session)
        await repo.add(link)
        await session.commit()


def _link(
    code: str,
    url: str = "https://target.example.com",
    *,
    disabled: bool = False,
    expires_at: datetime | None = None,
) -> Link:
    return Link(
        short_code=ShortCode(code),
        target_url=TargetUrl(url),
        created_at=datetime.now(UTC),
        expires_at=expires_at,
        disabled=disabled,
    )


# ---------------------------------------------------------------------------
# GET /{short_code} redirect
# ---------------------------------------------------------------------------


async def test_redirect_active_link_returns_307_with_location() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://target.example.com", "custom_code": "red1"})
        resp = await c.get("/red1")
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://target.example.com"


async def test_redirect_not_found_returns_404() -> None:
    async with await client() as c:
        resp = await c.get("/does-not-exist")
    assert resp.status_code == 404


async def test_redirect_expired_link_returns_410() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    await _seed_link(_link("redexp", expires_at=past))
    async with await client() as c:
        resp = await c.get("/redexp")
    assert resp.status_code == 410


async def test_redirect_disabled_link_returns_404() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://target.example.com", "custom_code": "reddis"})
        await c.post("/links/reddis/disable")
        resp = await c.get("/reddis")
    assert resp.status_code == 404
