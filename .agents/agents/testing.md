# Testing rules

- Use `pytest`.
- Do not use `unittest.TestCase`, `setUp`, `tearDown`.
- Put `from __future__ import annotations` in every test file.
- **The project is fully async**: FastAPI handlers are async, the service is async, the repository is async. All tests are **`async def`** too; DB fixtures are `async`.
- `pyproject.toml` sets `asyncio_mode = "auto"` — `async def test_X()` runs without `@pytest.mark.asyncio`.

## Unit tests

- Unit tests must be fast and isolated.
- Do not share state between tests.
- Do not test the API in unit tests.
- Do not use `MagicMock`, `patch` or `unittest.mock` if a Fake object can do the job.
- **A Fake repository mirrors the real one's async signature**: all methods are `async def`, so that `await self.repository.X(...)` in the service works.
- Test functions are `async def`; service calls go through `await`.

~~~python
class FakeRepository:
    def __init__(self) -> None:
        self._store: dict[str, Link] = {}
        self._next_id: int = 1

    async def add(self, link: Link) -> Link:
        stored = replace(link, id=self._next_id)
        self._store[stored.code] = stored
        self._next_id += 1
        return stored

    async def get_by_code(self, code: str) -> Link | None:
        return self._store.get(code)
~~~

- Fake objects are preferable to the mock approach.
- For in-memory storage you can use a `dict`, a simple ID counter, and `replace()` for immutable copies.
- If a method must signal a missing entity — check `is None`.
- For errors, use `pytest.raises(..., match=...)`.
- Test names — in the `test_...` style.

## What to check in unit tests

- Happy path.
- Edge cases: empty string, `None`, `0`, whitespace.
- Error cases: invalid input, missing entity.
- A regression test for the bug that was found.

## Integration tests

- Integration tests exercise the API end to end.
- HTTP client: `httpx.AsyncClient` over `ASGITransport` (invoked via `async with`).
- Test-environment state must be cleaned **before and after** every test — an autouse fixture with `async def`, cleanup via `await session.execute(text("DELETE FROM ..."))`.
- `pytest.fixture(autouse=True)` + `async def` is convenient for this.
- Assert real HTTP statuses and JSON responses.
- Set `follow_redirects=False` on `httpx.AsyncClient` explicitly. It is already the httpx default, but `starlette.testclient.TestClient` has the opposite default (`True`), and after migrating to it a test would silently follow the 307 redirect instead of checking `Location`.

## Coverage and evidence

- Every testing task explicitly declares its coverage scope: one module or the whole application.
- For a single module use `--cov=<python-module> --cov-branch --cov-report=term-missing --cov-fail-under=100`.
- The final project check always runs against the whole `app`:
  `uv run pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100`.
- The percentage must not be obtained by modifying `app/`, the coverage settings or exclusions. Forbidden:
  `skip`, `xfail`, `pragma: no cover` and checks without a meaningful `assert`.
- The result is recorded in `reviews/<task>-coverage.md`: the exact command, date, verified
  commit SHA, the `passed` count, the final percentage, the `Missing` column (`none` at 100%), the levels
  of the added tests, and confirmation that no forbidden workarounds were used.
- The task is not complete until the declared scope has 100% branch coverage, all checks
  are green, and the report is stored in Git.
