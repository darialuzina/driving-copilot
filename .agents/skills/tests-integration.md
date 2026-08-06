# Skill: Integration Tests

## Algorithm for writing integration tests

### 1. Preparation
- Read `.agents/agents/testing.md` and `.agents/agents/database.md`.
- Integration tests verify the **full path**: HTTP request → API → Service → Repository → PostgreSQL.
- **The project is fully async**: handlers are async, the service is async, the repository is async, `AsyncSession` via DI.

### 2. Structure
- Files: `tests/integration/test_<endpoint>.py`.
- HTTP client: **`httpx.AsyncClient`** on top of `ASGITransport` (it is async and supports `async with`). Do not use the old sync client: it hides async errors and is a poor fit for a strict async project.
- A real test database (PostgreSQL in Docker).
- **The autouse table-cleanup fixture is async**, executed via `async with get_sessionmaker()() as session: await session.execute(text("DELETE FROM links"))` (the session factory from `app/db/session.py`).

### 3. Rules
- Only `pytest`, functions. No `unittest.TestCase`.
- **All test functions are `async def`** — `asyncio_mode = "auto"` in `pyproject.toml` runs them without `@pytest.mark.asyncio`.
- **The autouse cleanup fixture is also `async`**:
  ```python
  @pytest.fixture(autouse=True)
  async def clean_db() -> AsyncGenerator[None, None]:
      async with get_sessionmaker()() as session:
          await session.execute(text("DELETE FROM links"))
          await session.commit()
      yield
      async with get_sessionmaker()() as session:
          await session.execute(text("DELETE FROM links"))
          await session.commit()
```
- **AsyncClient is invoked via `async with`** or by creating the client in a fixture. Write **`follow_redirects=False`** explicitly — we need to test the 307 and `Location` themselves, not the final response (it is the default in httpx, but not in `TestClient`).
- Do not depend on test execution order.
- `-> None` annotations on every test function, `async def`.
- `from __future__ import annotations` as the first line of the file.

### Example test (async + httpx.AsyncClient)

```python
from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.db.session import get_sessionmaker
from app.main import app


@pytest.fixture(autouse=True)
async def clean_db() -> AsyncGenerator[None, None]:
    async with get_sessionmaker()() as session:
        await session.execute(text("DELETE FROM links"))
        await session.commit()
    yield
    async with get_sessionmaker()() as session:
        await session.execute(text("DELETE FROM links"))
        await session.commit()


async def test_post_link_returns_201() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", follow_redirects=False) as client:
        response = await client.post("/links", json={"url": "https://example.com"})
        assert response.status_code == 201
        body = response.json()
        assert body["short_code"]
        assert body["target_url"] == "https://example.com"
        assert body["clicks"] == 0
```

### 4. What to test

**Not just the happy path.** Every endpoint must have tests in three categories:

- **Happy path** — valid request → expected success (200/201, correct JSON body, data in the DB).
- **Boundary cases** — values **at the edge** of the allowed range. For example, a URL of length 2048 (the maximum) — must be accepted; a URL of length 2049 — must be rejected. Boundary tests catch off-by-one errors.
- **Invalid input** — what the API returns on an empty URL, on `"not-a-url"`, on a missing field, on a trailing slash, on exceeded limits. Expect 422 (not 500). For a nonexistent resource — 404.

Plus, for a bugfix — a **regression test** for the specific problem (see `.agents/skills/bugfix.md`).

Concrete items:

- All HTTP methods of the endpoint (GET, POST, PUT/PATCH, DELETE).
- Response codes (200, 201, 404, 422) — all branches, not just the successful one.
- Response body — JSON structure, check specific fields (`assert body["short_code"]`, not just `body is not None`).
- That data is actually saved/deleted in the DB (via `await session.execute(select(...))` after the request).
- Response headers when they matter (Location on a 307 redirect, Content-Type on a JSON response).

### 5. Verify
- `uv run ruff format .` — auto-formatting.
- `uv run ruff check --fix .` — auto-fix the auto-fixable rules.
- `uv run ruff check .` — must be green.
- `uv run basedpyright`
- `uv run pytest tests/integration/ -q` — all tests green, no warnings about the event loop or sync-in-async.

### 6. Coverage and report

Coverage is a mandatory gate, not an informational number. For the full test scope, run:

```bash
uv run pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100
```

For a scoped task, replace `app` with the explicitly named Python module. The declared scope
must reach 100% of lines and branches. You may not change `app/`, `pyproject.toml`, coverage
exclusions, or use `skip`, `xfail`, `pragma: no cover`, or empty checks for the sake of the percentage.

Save `reviews/<task>-coverage.md` with the following evidence:

- the exact command and run date;
- the verified commit SHA;
- the `passed` count and the final percentage;
- the `Missing` value (`none` at 100%);
- which endpoints and test levels were added;
- confirmation of the absence of `skip`, `xfail`, `pragma: no cover`, and vacuous `assert`s.

The task is not complete until coverage reaches 100%, the checks are green, and the report is saved.
