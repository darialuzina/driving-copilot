# Skill: Unit Tests

## Algorithm for writing unit tests

### 1. Preparation
- Read `.agents/agents/testing.md` — the testing strategy.
- Unit tests exercise the **service layer** in isolation from the DB.
- **The project is fully async**: `LinkService` is async, `LinkRepository` is async. The tests are async too.

### 2. Structure
- Files: `tests/unit/test_<module>.py`.
- Factory: `make_service()` creates the service with a **Fake** repository.
- Fake repository: stores data in a plain `dict` — no DB, **with the same async signatures** as the real `LinkRepository` (methods are `async def`, otherwise `await self.repository.X(...)` in the service breaks).

### 3. Rules
- Only `pytest`, functions. No `unittest.TestCase`.
- **All test functions are `async def`** — our `pyproject.toml` has `asyncio_mode = "auto"`, so pytest runs them in the event loop without `@pytest.mark.asyncio`.
- Mocks — Fake classes only. No `MagicMock`, no `patch`.
- Fake repository — **all methods `async def`**, even if the body is just `return self._store[code]`. Signatures must match the real `LinkRepository` (`add`, `get_by_code`, `list_all`, `update` — all async).
- Each test creates its own service instance via the factory.
- `-> None` annotations on every test function.
- `pytest.raises(ErrorClass, match=...)` — always with `match=` and a message fragment.
- `from __future__ import annotations` as the first line of the file.

### 4. What to test
- The happy path.
- Boundary cases (empty string, None, duplicates).
- Error cases (nonexistent ID, invalid input).

### Example Fake repository (async)

```python
class FakeLinkRepository:
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

    async def list_all(self, limit: int = 100) -> list[Link]:
        return list(self._store.values())[:limit]

    async def update(self, link: Link) -> Link:
        self._store[link.code] = link
        return link
```

### Example test (async)

```python
async def test_create_link_valid_url_returns_link() -> None:
    service = make_service()
    link = await service.create_link("https://example.com")
    assert link.code
    assert link.target_url == "https://example.com"


async def test_create_link_invalid_url_raises() -> None:
    service = make_service()
    with pytest.raises(InvalidUrlError, match="scheme must be http or https"):
        await service.create_link("not-a-url")
```

### 5. Verify

**The verification step is mandatory — the task is not considered complete until all commands below have been run and their output shown.**

- `uv run ruff format .` — auto-formatting.
- `uv run ruff check --fix .` — auto-fix the auto-fixable rules (`I001`, `F401`, etc.).
- `uv run ruff check .` — must be green.
- `uv run basedpyright` — strict typing (including the tests).
- `uv run pytest tests/unit/ -q` — **run pytest via the command-execution tool and show the output**. Do not claim "the tests will pass" without an actual run.
- If pytest fails (IndentationError, SyntaxError, ImportError, AssertionError, AttributeError) — **fix the file and rerun pytest**. Repeat until it says `passed`.
- Include the pytest summary line (`N passed in Xs` or `N failed`) in the final answer — otherwise the task is not done.

### 6. Coverage and report

For a unit-test task, measure exactly the module under test. For example, for `LinkService`:

```bash
uv run pytest tests/unit/test_link_service.py --cov=app.services.link_service --cov-branch --cov-report=term-missing --cov-fail-under=100
```

For the final test pass over the whole project, this command is mandatory:

```bash
uv run pytest --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=100
```

You may not change `app/`, `pyproject.toml`, coverage exclusions, or use `skip`, `xfail`,
`pragma: no cover`, or empty checks for the sake of the percentage.

Save `reviews/<task>-coverage.md`: the exact command, date, verified commit SHA,
the `passed` count, the percentage, `Missing` (`none` at 100%), the covered scenarios, and
confirmation that no forbidden workarounds were used. The task is not complete until the
declared scope has 100% branch coverage, or while checks are red or the report is not saved.
