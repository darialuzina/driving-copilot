# Skill: Code Review

## Goal

Verify that the code meets the standards in `.agents/agents/python-standards.md`
and the architecture rules in `.agents/agents/architecture.md`.

***

## Algorithm

### 1. Run the automated checks

~~~bash
uv run ruff check <file_or_folder>
uv run basedpyright <file_or_folder>
~~~

Include the results in the report. Do not restate the automated errors — summary only.

### 2. Read the files under review in full

### 3. Check against the checklist

#### 🔴 Blocking (merge forbidden until fixed)

- [ ] `from __future__ import annotations` — first line of the file
- [ ] All function parameters are annotated
- [ ] All functions have a return type annotation (including `-> None`)
- [ ] No `Optional[X]`, `List[X]`, `Dict[K,V]` — only `X | None`, `list[X]`, `dict[K,V]`
- [ ] No `-> dict` as a public contract — only DTO/Value Object
- [ ] The service layer does not import `db/models.py` directly
- [ ] No business logic in route handlers
- [ ] No `except Exception: pass`
- [ ] No mutable default values (`= []`, `= {}`)
- [ ] **Async rules (§5):** the project is fully async — no `from sqlalchemy.orm import Session` (only `AsyncSession`), all DB methods are `async def` + `await session.execute(...)`, the service calls the repository via `await`, handlers are `async def` + `await service.X(...)`. A sync call in an async context blocks the event loop and kills performance.
- [ ] **No `next(generator_func())` on async generators** — it simply does not work (use `anext()` or `async for`). A telltale sign of copy-paste from old sync code.
- [ ] **Logging (§13):** no `print()`, no f-strings in `logger.info(...)`, no secrets / tokens / Authorization in kwargs.
- [ ] **Security (§14):** no hardcoded secrets, SQL is parameterized, passwords via `bcrypt`/`argon2`, HTTP clients with `timeout=` and `verify=True`, `subprocess` without `shell=True` on user input.

#### 🟡 Non-critical (recommendations, fix in the next PR)

- [ ] No magic numbers — only named constants
- [ ] No duplicated logic (DRY)
- [ ] A function does one thing (SRP), no longer than 30-40 lines
- [ ] Naming: `snake_case` / `PascalCase` / `UPPER_SNAKE_CASE`
- [ ] Parallel tasks via `asyncio.TaskGroup`, not `gather()` (when `return_exceptions=True` is not needed) — §5
- [ ] Modern syntax: `type UserId = int` (PEP 695), `Self`, `match/case`, `StrEnum` where appropriate — §15
- [ ] Application coverage stays at 100% (`--cov-fail-under=100`)

***

## Report format

~~~text
## Code Review: <file or branch>

### Automated checks
ruff: X errors | basedpyright: Y errors

### Violations

#### 🔴 Blocking

| # | File | Line | Violation | Standard |
|---|------|--------|-----------|----------|
| 1 | bad_link_service.py | 1 | Missing `from __future__ import annotations` | python-standards §1 |

#### 🟡 Non-critical

| # | File | Line | Violation | Standard |
|---|------|--------|-----------|----------|
| 1 | bad_link_service.py | 45 | Magic number `75` | python-standards §8 |

### Summary
- Blocking: X
- Recommendations: Y
- Verdict: ❌ Needs changes / ✅ Can be accepted
~~~

***

## Example prompt

~~~text
Read the file .agents/skills/code-review.md (it references .agents/agents/python-standards.md, .agents/agents/code.md, and .agents/agents/architecture.md itself).

Perform a code review of app/services/bad_link_service.py.

First run:
uv run ruff check app/services/bad_link_service.py
uv run basedpyright app/services/bad_link_service.py

Then do the manual check against the checklist in .agents/skills/code-review.md.
Produce the report in the format from .agents/skills/code-review.md.
~~~
