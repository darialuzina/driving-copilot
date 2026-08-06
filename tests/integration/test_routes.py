from __future__ import annotations

from httpx import ASGITransport, AsyncClient

from app.main import app


async def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# POST /links
# ---------------------------------------------------------------------------


async def test_post_link_with_generated_code_returns_201() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "https://example.com"})
    assert resp.status_code == 201
    body = resp.json()
    assert body["short_code"]
    assert body["target_url"] == "https://example.com"
    assert body["status"] == "active"
    assert body["clicks"] == 0
    assert body["disabled"] is False
    assert body["short_url"].endswith(body["short_code"])


async def test_post_link_with_custom_code_returns_201() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "https://example.com", "custom_code": "mycode"})
    assert resp.status_code == 201
    assert resp.json()["short_code"] == "mycode"


async def test_post_link_with_ttl_sets_expires_at() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "https://example.com", "ttl_seconds": 3600})
    assert resp.status_code == 201
    assert resp.json()["expires_at"] is not None


async def test_post_link_invalid_url_returns_422() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "not-a-url"})
    assert resp.status_code == 422


async def test_post_link_loopback_url_returns_422() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "https://localhost"})
    assert resp.status_code == 422


async def test_post_link_invalid_custom_code_returns_422() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"url": "https://example.com", "custom_code": "abc"})
    assert resp.status_code == 422


async def test_post_link_duplicate_custom_code_returns_409() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://a.com", "custom_code": "taken1"})
        resp = await c.post("/links", json={"url": "https://b.com", "custom_code": "taken1"})
    assert resp.status_code == 409


async def test_post_link_missing_url_returns_422() -> None:
    async with await client() as c:
        resp = await c.post("/links", json={"custom_code": "nocode"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /links
# ---------------------------------------------------------------------------


async def test_get_links_empty_returns_empty_list() -> None:
    async with await client() as c:
        resp = await c.get("/links")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_get_links_returns_list() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://a.com", "custom_code": "rr01"})
        await c.post("/links", json={"url": "https://b.com", "custom_code": "rr02"})
        resp = await c.get("/links")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2
    codes = {item["short_code"] for item in body}
    assert codes == {"rr01", "rr02"}


# ---------------------------------------------------------------------------
# GET /links/{short_code}
# ---------------------------------------------------------------------------


async def test_get_link_found_returns_200() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://a.com", "custom_code": "gg01"})
        resp = await c.get("/links/gg01")
    assert resp.status_code == 200
    assert resp.json()["short_code"] == "gg01"


async def test_get_link_not_found_returns_404() -> None:
    async with await client() as c:
        resp = await c.get("/links/missing")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /links/{short_code}/disable
# ---------------------------------------------------------------------------


async def test_disable_link_found_returns_200_disabled() -> None:
    async with await client() as c:
        await c.post("/links", json={"url": "https://a.com", "custom_code": "dd01"})
        resp = await c.post("/links/dd01/disable")
    assert resp.status_code == 200
    body = resp.json()
    assert body["disabled"] is True
    assert body["status"] == "disabled"


async def test_disable_link_not_found_returns_404() -> None:
    async with await client() as c:
        resp = await c.post("/links/missing/disable")
    assert resp.status_code == 404
