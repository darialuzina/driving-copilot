# Python Development Standards

The project's development standard. This document is the single source of verifiable rules. Paragraph references like "§5", "§13" are used in `.agents/agents/code.md` and `.agents/skills/code-review.md`. All rules are mandatory for new code. Legacy code is brought up to the standard as you touch it.

***

## Core principles

1. **Readability first.** Code is read more than it is written. Gratuitous list comprehensions just to save lines — no; an explicit `for` when it is clearer — yes. Clever "fast" code — only when profiling has shown it is a bottleneck.
2. **No types, no project.** Every function and method has parameter and return type annotations, including `-> None`. `basedpyright` in strict mode is mandatory.
3. **Dicts are evil at boundaries.** `dict` is forbidden as a public contract between modules / layers / services. Inside a single function, `dict` is acceptable as an intermediate structure. At boundaries — `dataclass` / Pydantic / domain objects.
4. **Secrets never land in code or commits.** Only via `.env` (locally) and environment variables (on servers). Any API key in `pyproject.toml`, tests, or examples is a bug, not a feature.
5. **Local checks pass before every commit.** One shortcut: `uv run ruff check . && uv run basedpyright && uv run pytest -q`. If it fails — the commit does not go out.
6. **An async project stays async.** Any sync DB call in an async context blocks the event loop and wipes out the benefit of async FastAPI. See §5 below.

***

## Prohibitions — a violation blocks merge

| # | Construct | Why it is forbidden |
|---|---|---|
| 1 | `except Exception: pass` | Silences errors without a diagnosis. The source of "random" production crashes. Catch a specific type, or log and re-raise. |
| 2 | `def foo(items=[])` | A mutable default is shared between calls. Thousands of bugs in Python tutorials come from this example. Use `items: list[X] \| None = None` + `if items is None: items = []`. |
| 3 | `def get_stats() -> dict` | `dict` as a public contract cannot be typed. Use a DTO / dataclass / Pydantic. |
| 4 | `from sqlalchemy.orm import Session` in new code | The project is async. Only `AsyncSession` from `sqlalchemy.ext.asyncio`. |
| 5 | Synchronous `requests` / `psycopg.connect` in an async handler | Blocks the event loop. Use `httpx.AsyncClient` / `AsyncSession`. |
| 6 | `Optional[X]` / `List[X]` / `Dict[K, V]` | Obsolete pre-PEP-604 style. Use `X \| None` / `list[X]` / `dict[K, V]`. |
| 7 | Magic numbers in logic (`if len(x) > 255`) | Not self-documenting. Extract into named constants at the top of the module. |
| 8 | Business logic in a route handler (`api/links.py`) | Violates the layered architecture. Logic goes in `services/`; the handler only parses the request and builds the response. |
| 9 | `# noqa` / `# type: ignore` without an explanation | Suppressing the linter without a reason is untracked tech debt. If you add one — add a comment explaining **why**. |
| 10 | `--no-verify` / `SKIP=hook git commit` | Bypassing pre-commit. Never. If a hook fails — investigate, don't bypass (see AGENTS.md). |
| 11 | `print()` for logging | No level, no fields, doesn't reach centralized collection. Use `structlog` (see §13). |
| 12 | `logger.info(f"order {order_id} done")` | Every event is unique; aggregation by template becomes impossible. `logger.info("order done", order_id=order_id)` (see §13). |
| 13 | Secrets / tokens / Authorization headers in logger kwargs | Logs go to centralized collection → PII leak. See §13 and `.agents/agents/security.md`. |
| 14 | `httpx.get(url, verify=False)` / `requests.get(url, verify=False)` | MITM-vulnerable. For an internal CA — `verify="/path/to/ca.pem"`. See §14 and `.agents/agents/security.md`. |
| 15 | HTTP client without `timeout=` | The request can hang forever; in async, the task never releases the event loop. See §5 and §14. |
| 16 | `subprocess.run(..., shell=True)` with user input | Command injection. Only the list form + absolute path + restricted env. See §14. |

***

## §1. Typing

### Annotations are mandatory everywhere

~~~python
# ❌ No annotations
def create_link(url, disabled=False):
    return {"id": 1, "url": url}

# ✅
def create_link(url: str, disabled: bool = False) -> Link:
    return Link(id=1, target_url=url, disabled=disabled)
~~~

### `from __future__ import annotations` — the first line of the file

Lets you write `X | None`, `list[X]` without issues on any Python version; annotations become lazy (not evaluated at import time), which eliminates circular imports in type hints.

### Modern style — PEP 604 (`X | Y`) and PEP 585 (`list[X]`, `dict[K, V]`)

~~~python
# ❌ Obsolete style
from typing import Optional, List, Dict, Union
def find(id: int) -> Optional[Link]: ...
def items() -> List[Dict[str, int]]: ...

# ✅ Modern style
def find(id: int) -> Link | None: ...
def items() -> list[dict[str, int]]: ...
~~~

### A `None` return — always annotated

~~~python
# ❌
def clear_cache(self):
    self._cache = {}

# ✅
def clear_cache(self) -> None:
    self._cache = {}
~~~

### Protocol — for abstractions between layers

A service depends on `LinkRepositoryProtocol`, not on the concrete `LinkRepository`. This lets you swap in a Fake in tests without touching the real database.

***

## §2. Value Objects and DTOs

`dict` is forbidden as a **public** function return — at module boundaries the contract must be typed.

### Value Object — an immutable domain entity

~~~python
@dataclass(frozen=True)
class Link:
    id: int
    code: str
    target_url: str
    clicks: int
    expires_at: datetime | None
~~~

### DTO — data between layers

~~~python
@dataclass(frozen=True)
class LinkStatsDTO:
    total_links: int
    total_clicks: int
    avg_clicks_per_link: float
~~~

### Where `dict` is acceptable

Only as a **private intermediate structure inside a single function**, never as the return type of a public API.

***

## §3. Exception handling

### Don't swallow without logging

~~~python
# ❌
try:
    result = risky()
except Exception:
    pass
~~~

### Catch a specific type

~~~python
# ❌ Too broad an except
try:
    parsed = urlparse(value)
except Exception:
    return False

# ✅ Specific type
try:
    parsed = urlparse(value)
except ValueError:
    return False
~~~

`except Exception` is acceptable **only at the outermost point** (FastAPI middleware, top-level async loop), and even then with logging.

### Fail fast

If the application started with broken configuration (missing `DATABASE_URL`, malformed `AGENTPLATFORM_API_KEY`) — it is better to crash at startup than to limp along "somehow" and crash at 3 a.m.

### Don't mask errors by returning `None`

If a function "may not succeed" for business reasons (link not found) — `None` is justified. If for technical reasons (DB unavailable) — propagate the exception, don't return `None`. Otherwise the caller thinks "no data" when really "the connection failed".

***

## §4. SOLID

### S — Single Responsibility

One class / function — one reason to change.

~~~python
# ❌ Computes, formats, and saves
def process_links(links: list[Link]) -> str:
    rate = len([link for link in links if not link.disabled]) / len(links) * 100
    report = f"Active rate: {rate:.1f}%"
    save_to_file(report)
    return report

# ✅ Separated
def calculate_active_rate(links: list[Link]) -> float: ...
def format_rate(rate: float) -> str: ...
def save_report(text: str, path: Path) -> None: ...
~~~

### D — Dependency Inversion

The service depends on a `Protocol`, not on a concrete implementation.

~~~python
class LinkRepositoryProtocol(Protocol):
    async def get_by_code(self, code: str) -> Link | None: ...
    async def update(self, link: Link) -> Link: ...

class LinkService:
    def __init__(self, repo: LinkRepositoryProtocol) -> None:
        self.repo = repo
~~~

***

## §5. Async rules — this project is fully async

The project is built on FastAPI + `AsyncSession` + async psycopg. Any sync insertion into this stack kills performance regardless of profiling.

### Checks performed in code review

- [ ] All repository methods are `async def`; all DB access goes through `await session.execute(...)` / `await session.commit()`.
- [ ] The service calls the repository via `await` and is itself `async def`.
- [ ] The route handler is `async def`; service calls go through `await`.
- [ ] No `from sqlalchemy.orm import Session` — only `from sqlalchemy.ext.asyncio import AsyncSession`.
- [ ] No sync HTTP clients (`requests.get`) in an async handler — `httpx.AsyncClient` or `aiohttp`.
- [ ] No `time.sleep()` in an async function — `await asyncio.sleep(...)`.
- [ ] Async generators are iterated via `async for` / `anext()`, not via `next()`.

### Signs of a sync leak

If `psycopg`/SQLAlchemy complain in the logs about "attempted to call non-async method on AsyncSession", or the ASGI stack emits a RuntimeWarning about "coroutine was never awaited" — there is a sync insertion somewhere. Find it and fix it, don't suppress it.

### Parallel tasks — `asyncio.TaskGroup`, not `gather`

For multiple parallel tasks, prefer `asyncio.TaskGroup` (Python 3.11+) over `asyncio.gather`:

~~~python
# ✅ TaskGroup — cancels the remaining tasks on error, caught via ExceptionGroup
async def process_batch(ids: list[int]) -> list[User]:
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch_user(uid)) for uid in ids]
    return [t.result() for t in tasks]
~~~

Reserve `gather(*coros, return_exceptions=True)` for cases where errors are **handled individually** per task (e.g. a partial export where one failure must not abort the rest).

### Timeouts on external calls — mandatory

~~~python
# ✅
try:
    result = await asyncio.wait_for(fetch_data(), timeout=5.0)
except TimeoutError:
    logger.error("fetch_data timed out")
    raise
~~~

Any external call (HTTP, DB, queue) without an explicit timeout is an anti-pattern. In `httpx.AsyncClient`, use `httpx.Timeout(connect, read, write, pool)` (see `.agents/agents/security.md` §6).

***

## §6. KISS — Keep It Simple

Signs of a violation:
- a function longer than ~40 lines;
- nesting deeper than 3 levels of `if`/`for`/`try`;
- flag parameters (`mode="fast"`, `use_cache=True`) — usually two functions under one name; better to split.

~~~python
# ❌
def is_valid_title(title: str) -> bool:
    return bool(
        title is not None and isinstance(title, str)
        and len(title.strip()) > 0 and not title.strip() == ""
    )

# ✅
def is_valid_title(title: str) -> bool:
    return bool(title.strip())
~~~

***

## §7. DRY — Don't Repeat Yourself

The same logic lives in one place. If something gets copied from file to file (`fetch_with_retry`, date formatting, URL parsing) — extract it into a utility or a shared module function.

But: premature abstraction (a function used once, extracted "just in case") is worse than a duplicate in two places. The rule of three — extract on the third duplicate.

***

## §8. Naming and constants

| What | Style | Example |
|-----|-------|--------|
| Functions / methods | `snake_case` | `create_link`, `get_by_code` |
| Classes | `PascalCase` | `LinkService`, `LinkRepositoryProtocol` |
| Module constants | `UPPER_SNAKE_CASE` | `MAX_URL_LENGTH = 2048` |
| Booleans | `is_*`, `has_*` | `is_archived`, `has_clicks` |
| Private members | `_*` (single underscore) | `_generate_code` |

~~~python
# ❌ Magic numbers
if len(title) > 255: ...
if rate > 75: ...

# ✅
MAX_TITLE_LENGTH: int = 255
COMPLETION_RATE_EXCELLENT: float = 75.0
~~~

***

## §9. Function arguments

### Mutable defaults — forbidden

~~~python
# ❌
def process(items: list[str] = []) -> list[str]: ...

# ✅
def process(items: list[str] | None = None) -> list[str]:
    if items is None:
        items = []
    ...
~~~

### Too many parameters — pack them into a DTO

More than 4-5 parameters is a sign the function knows about too many things. Combine them into a `dataclass` / Pydantic model.

### Preferably: a single return point

Not a rule, but it makes reading easier. Especially when the return value is a DTO with a dozen fields.

***

## §10. Layered architecture

The project follows the split `api/` → `services/` → `repositories/` → `db/models.py`. Domain entities live in `domain/`. Each layer imports **only the layer below it**.

| Layer | Imports | Does not import |
|------|------------|----------------|
| `domain/` | nothing from the project | everything project-level |
| `db/models.py` | `domain/` (optionally) | `services/`, `api/` |
| `repositories/link_repository.py` | `domain/`, `db/models.py` | `services/`, `api/` |
| `services/` | `domain/`, repository Protocol | `db/models.py` directly |
| `api/` | `services/`, `domain/` | `db/`, `repositories/` directly |
| `validators/` | `domain/` (if needed) | `db/`, `services/`, `api/` |

Concrete rules:
- The API does not reach into `LinkRepository` past the service, even "just to be faster" — you lose the single point of validation.
- The service does not touch `LinkModel` (the SQLAlchemy model) directly — only via the repository.
- Business logic **does not live** in the route — the handler parses the request, calls the service, and builds the response.

***

## §11. Database and migrations

- Every DB query goes through a **repository** — not directly from a service and not from a route.
- Complex `JOIN`s/aggregations live in the repository as a dedicated method returning a typed DTO — no "return a `Row` and unpack it upstream".
- Schema changes — only via an Alembic migration. No `Base.metadata.create_all(engine)` outside of `tests/`.
- `alembic upgrade head` runs **before** application startup (in this project — as a separate `uv run alembic upgrade head` command in the runbook or deploy script, not from `app.startup`).
- Long migrations (index creation, backfills) — a separate migration; no `op.execute(...)` on blocking DDL without `CONCURRENTLY`.

***

## §12. Documentation — see `.agents/agents/docs.md`

Every public function / method / class **must have a docstring** — this is part of the code standard, not a separate task. Without a docstring, code **does not merge**.

Brief rules (details and formats in `.agents/agents/docs.md`):

- **Docstring** on every public function/method/class. Format — Google-style: a one-line summary, then `Args:` / `Returns:` / `Raises:` if needed. **Language — English**.
- **CHANGELOG.md** is updated for any user-visible change, under `[Unreleased]` → `Added` / `Changed` / `Fixed` / `Deprecated` / `Removed` / `Security`. Internal refactoring with no behavior change **does not go into the CHANGELOG**.
- **ADR** in `docs/adr/NNNN-short-name.md` — when a decision affects multiple modules or changes a public contract. Required sections: Status, Context, Decision, Consequences.
- **README.md** — updated when endpoints, ENV variables, launch commands, or dependencies change. A stale README is a merge blocker.

Forbidden (blocks merge):

- Committing a public API without a docstring.
- A docstring that repeats the function name (`def get_user(): """Get user."""`) — better no docstring than a junk one.
- A new endpoint / breaking change without a CHANGELOG entry.

***

## §13. Logging — see `.agents/agents/logging.md`

Structured logging is a mandatory part of the standard. Details (structlog configuration, redact_secrets, middleware with `request_id`) are in `.agents/agents/logging.md` (the file is created in Step 8.1.2). The workshop itself does not create the `app/logging.py` and `app/middleware/request_id.py` modules: they are reference fragments you add yourself if you bring logging up to production quality. Here are the verifiable rules that get caught in code review.

### What to use

- **Service / application** — `structlog` (JSON in prod, ConsoleRenderer in dev).
- **Library / package** — the standard `logging` module (don't impose a format on the consumer).
- `print()` for logging is **forbidden** — no levels, no fields, doesn't reach centralized collection.

### Levels

| Level | When |
|---|---|
| `debug` | Details for local debugging; disabled in prod |
| `info` | Significant events: startup, task completion, business event |
| `warning` | An abnormal situation the code recovered from (retry, fallback) |
| `error` | An error, the operation failed — needs attention |
| `critical` | The service is non-functional — needs an immediate response |

### Rules (a violation blocks merge)

- **kwargs, not f-strings** in the message. The event message stays stable, parameters go separately — otherwise aggregation by template is impossible:

~~~python
# ❌
logger.info(f"Processing order {order_id}")

# ✅
logger.info("processing order", order_id=order_id)
~~~

- **Don't log secrets.** Passwords, tokens, PII, Authorization headers, cookies — never. In the structured pipeline the recursive `redact_secrets` processor runs (details in `.agents/agents/logging.md`), but that is the last line of defense — there must be no explicit secrets at the `logger.info(...)` level.
- **Don't log in hot loops.** A log in the hot path under load turns into an I/O bottleneck. Log the loop's summary, or sample.
- **`request_id` / `trace_id` via `structlog.contextvars`.** FastAPI middleware binds `request_id` at the start of the request (`bind_contextvars`) and clears it at the end (`clear_contextvars`). All logs within the request automatically get this field.
- **Prod format is JSON.** One line = one JSON object. ELK / Loki / Datadog need this for parsing.

***

## §14. Security — see `.agents/agents/security.md`

Applied Python security — the extended set of patterns is in `.agents/agents/security.md` (the "Python security patterns" section). Here are three principles and a compact code-review checklist.

### Principles

1. **Don't trust input data.** Everything that arrives from outside (HTTP body, query, header, Kafka, file, CLI argument) is validated via Pydantic at the system boundary, not deep inside.
2. **Least privilege.** Every service, process, token, IAM role operates with the minimal set of permissions.
3. **Defense in depth.** Don't rely on a single line of defense. SQL injection — parameterization **and** ORM **and** input validation **and** a least-privilege DB user.

### Security checklist (every review)

- [ ] Secrets — only via ENV / vault; not in code, not in logs, not in the gitleaks diff.
- [ ] SQL queries are parameterized (or go through the ORM); no f-strings in `execute(...)`.
- [ ] Input data is validated at the boundary via Pydantic.
- [ ] Passwords — `bcrypt` / `argon2`, not `md5` / `sha1` / plain.
- [ ] Token / secret comparison — `hmac.compare_digest`, not `==`.
- [ ] Randomness for security — `secrets.token_urlsafe`, not `random`.
- [ ] HTTP client — with an explicit `timeout=`, `verify=True`, no `follow_redirects` if the user controls the URL.
- [ ] `subprocess` — `shell=False`, absolute path, restricted env, `timeout=`.
- [ ] `pickle` / `yaml.load` / `xml.etree` without `defusedxml` — **never use** on untrusted input.
- [ ] File upload — MIME by content (`python-magic`), UUID filename, re-encoding (for images — via Pillow).
- [ ] JWT decode — explicit `algorithms=[...]`, verify `aud` / `iss` / `exp`.

Details and examples — in `.agents/agents/security.md`.

***

## §15. Modern Python 3.14 features

The project targets Python >=3.14. This means all 3.10+, 3.11+, 3.12+, 3.13+, 3.14+ features are available. Using them **directly** is code style, not "optional".

### `match/case` instead of long `if/elif` chains over structure (3.10+)

~~~python
# ✅
def handle_event(event: dict[str, object]) -> str:
    match event:
        case {"type": "link_created", "id": int(link_id)}:
            return f"new link: {link_id}"
        case {"type": "link_deleted"}:
            return "link removed"
        case {"type": str(unknown)}:
            return f"unknown event: {unknown}"
        case _:
            return "malformed event"
~~~

`if isinstance(...) and "x" in dct and ...` — rewrite as `match` when there are ≥ 3 branches and they branch on structure.

### `Self` for fluent interfaces (3.11+)

~~~python
from typing import Self

class QueryBuilder:
    def where(self, predicate: str) -> Self:
        self._predicates.append(predicate)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self
~~~

This used to require `TypeVar('Q', bound='QueryBuilder')` plus forward references — now it is a single annotation.

### `ExceptionGroup` (3.11+) + `TaskGroup`

See §5 — for concurrent code where several tasks can fail simultaneously, errors arrive as a batch via `ExceptionGroup`:

~~~python
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(fetch_users())
        tg.create_task(write_audit_log())
except* DatabaseError as eg:
    for err in eg.exceptions:
        logger.error("db error in batch", err=str(err))
~~~

`except*` is dedicated syntax for unpacking an `ExceptionGroup` by type.

### PEP 695 — new type alias syntax (3.12+)

~~~python
# ❌ Old style (TypeAlias from typing)
from typing import TypeAlias
UserId: TypeAlias = int
Maybe = list[int] | None

# ✅ PEP 695
type UserId = int
type Maybe[T] = T | None
type Point = tuple[float, float]
~~~

On 3.14 — use the new syntax. Keep the old `TypeAlias` import only when supporting versions below 3.12 (we are on 3.14, so not our case).

### `enum.StrEnum` (3.11+) for string constants

~~~python
# ✅
from enum import StrEnum

class LinkStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"

# Comparison with a plain string works directly
if status == "active": ...
~~~

`StrEnum` over `Enum` saves boilerplate and works with JSON / DB / API without `.value`.

### Parenthesized `with` for multiple resources (3.10+)

~~~python
# ❌ Long nesting
with open("input.txt") as src:
    with open("output.txt", "w") as dst:
        dst.write(src.read())

# ✅ 3.10+ — with parentheses
with (
    open("input.txt", encoding="utf-8") as src,
    open("output.txt", "w", encoding="utf-8") as dst,
):
    dst.write(src.read())
~~~

### `@dataclass(slots=True, frozen=True)`

`slots=True` saves memory (no `__dict__` on the instance) and **catches attribute typos** — `link.clcks = 5` fails with `AttributeError` instead of silently creating a new field. `frozen=True` forbids mutation — mandatory for Value Objects.

***

## Pre-commit self-check checklist

**Types and structure**

- [ ] `from __future__ import annotations` in every new file
- [ ] All parameters and return types annotated (including `-> None`)
- [ ] No `Optional[X]` / `List[X]` / `Dict[K, V]` (PEP 604/585)
- [ ] Returned data is a DTO / Value Object / domain object, not a `dict`
- [ ] No `except Exception: pass`; specific exception types
- [ ] No mutable defaults
- [ ] Magic numbers extracted into constants

**Architecture and async (§5, §10)**

- [ ] Async layers contain no sync calls to DB / HTTP / sleep
- [ ] Parallel tasks via `asyncio.TaskGroup`; external calls with `asyncio.wait_for(..., timeout=...)`
- [ ] The service does not import `db/models.py` directly
- [ ] No business logic in route handlers

**Logging (§13)**

- [ ] No `print()` for logging — only `structlog` / `logging`
- [ ] Messages without f-strings: `logger.info("event", key=value)`, not `logger.info(f"event {value}")`
- [ ] No secrets / tokens / PII in logger kwargs
- [ ] For the request lifecycle — `bind_contextvars(request_id=...)` in middleware

**Security (§14)**

- [ ] No hardcoded secrets / tokens / connection strings
- [ ] SQL is parameterized (or via ORM), no f-strings
- [ ] External data validated via Pydantic at the boundary
- [ ] Passwords — `bcrypt` / `argon2`; token comparison — `hmac.compare_digest`
- [ ] HTTP clients — with `timeout=`, `verify=True`, no `follow_redirects` for user-controlled URLs
- [ ] `subprocess` — `shell=False`, absolute path, restricted env, `timeout=`

**Documentation and changelog (§12)**

- [ ] Docstrings on new public functions / methods (Google-style, in English — see §12 and `.agents/agents/docs.md`)
- [ ] CHANGELOG.md updated if user-visible behavior changes

**Automated checks**

- [ ] `uv run ruff check .` — green
- [ ] `uv run basedpyright` — green
- [ ] `uv run pytest -q` — green, coverage gate `--cov-fail-under=100` passed
