# Code rules

- Always use `from __future__ import annotations`.
- Every function and method must have type annotations.
- If a function returns nothing, write `-> None` explicitly.
- Use modern Python 3.14+ syntax:
  - `X | None` instead of `Optional[X]`
  - `list[str]` instead of `List[str]`
- Write clear, short code with no unnecessary complexity.
- If logic repeats — extract it into helper functions.
- Do not mix HTTP logic, business logic, and SQL in one place.

## General principles

### PEP 8 — code style

- Follow PEP 8 for formatting (4-space indentation, max ~100 characters per line, snake_case for functions/variables, PascalCase for classes, UPPER_SNAKE for constants).
- Formatting and imports — via `ruff format` and `ruff check --fix`; do not argue with the style checker by hand.
- Names must be meaningful: `user_repository` is better than `ur`, `get_active_users()` is better than `gau()`.

### KISS — Keep It Simple, Stupid

- Pick the simplest solution that satisfies the requirement.
- Do not add abstractions "for the future" — add them when the second use case actually appears.
- A function must do one job; if the name begs for an `and` — split it in two.
- If a solution needs a long comment to explain "what is going on here" — it most likely needs simplifying, not commenting.

### DRY — Don't Repeat Yourself

- Repeated business logic goes into a helper / service / util — a single source of truth.
- Repeated constants and magic values go into named constants or an enum.
- But: DRY does not override KISS. Two similar pieces of code with different semantics are not a duplicate; do not merge them into one "universal" function with five flags.

### SOLID — designing classes and modules

- **S (Single Responsibility)** — one module / class / function is responsible for one thing. `UserService` must not send email — that is the job of a separate `EmailSender`.
- **O (Open/Closed)** — extend behavior by adding new classes/strategies, not by editing working code. A new notification type is a new class, not a new `if` branch in an old method.
- **L (Liskov Substitution)** — a subclass must behave like its base class. If `Repository.get()` returns `User | None`, then `CachedRepository.get()` returns the same — it does not throw an exception instead of `None`.
- **I (Interface Segregation)** — several narrow interfaces (`Reader`, `Writer`) are better than one fat `Repository` with every method, half of which go unused.
- **D (Dependency Inversion)** — pass dependencies via the constructor/parameters, do not hard-import them. A service takes `UserRepository` as a dependency rather than creating it internally — that gives testability and swappable implementations.

### Practical application in this project

- The layers (API / Service / Repository / Domain) are a direct consequence of SRP and Dependency Inversion.
- Fake objects in tests instead of `MagicMock` — that is Liskov (the fake behaves like the real thing) plus Dependency Inversion (the service does not know what it was given).
- FastAPI dependencies via `Depends(...)` and `dependency_overrides` — explicit top-down dependency passing, not global singletons.

## By layer

- The API layer (`app/api`) is responsible only for HTTP input and HTTP output (including mapping domain errors to HTTP).
- The Service layer (`app/services`) contains business logic and orchestration.
- The Repository layer (`app/repositories/link_repository.py`) works with SQLAlchemy and SQL and maps ORM models to domain entities.
- The Domain layer (`app/domain`) contains value objects, entities, and domain errors — with no dependencies on infrastructure.

## Returns and errors

- Repository methods may return `X | None`.
- Service methods may also return `X | None` if the entity is not found.
- The API layer must turn `None` into a proper HTTP response, e.g. `404 Not Found`.
- Do not hide errors inside route handlers.
- If input data is invalid — raise `ValueError` or a more precise exception.
- Never write `except Exception: pass`.
- If an exception is caught — either handle it meaningfully or re-raise.

## Forbidden

- Writing SQL directly in `app/api`.
- Using `print()` instead of proper code structure or logging.
- Duplicating the same business logic in multiple places.

## Linters and formatters

- Before finishing any task, always run:
  - `uv run ruff format .` — formats code per PEP 8.
  - `uv run ruff check --fix .` — fixes all auto-fixable rules (unsorted imports `I001`, unused `F401`, etc.).
- If `ruff check` is still red after `--fix` — the rule is not auto-fixable and must be fixed by hand (e.g. `F841` unused variable — delete the variable or use it).
- Do not silence warnings via `# noqa: CODE` without an explicit reason. If you have to silence one — leave a comment nearby explaining "why".
- All CI checks must be green before committing: `ruff format --check .`, `ruff check .`, `basedpyright`, `pytest`.
- The `I001` error (unsorted imports) is always fixed by `ruff check --fix` — do not leave it in the code and do not add it to `.gitignore`/`per-file-ignores`.

## Pre-commit and security hooks

- `git commit --no-verify` is forbidden. Never bypass pre-commit even if the problem is "not yours" — fix it or make a separate commit for the problem.
- If pre-commit failed on an error **from your changes** (ruff, basedpyright, pytest, bandit on new code) — fix it and re-run `git commit`. Do not ask the participant what to do.
- If pre-commit failed on **pip-audit** with a CVE in a dependency that is **not related to your changes** (a pre-existing problem):
  1. Set the current commit aside.
  2. Check which package version fixes the CVE (`pip index versions <package>` or the text of the advisory itself).
  3. Bump **only that package** in `pyproject.toml` (do not touch other dependencies while you are at it).
  4. Run `uv sync && uv run pytest -q` — make sure the tests are green on the new version.
  5. Make a **separate commit** touching only `pyproject.toml` + `uv.lock` with a message like `[manual] chore(deps): bump <package> to X.Y.Z for CVE-XXXX-XXXXX` (tag, scope, and description all in English).
  6. Then return to the original commit and finish it normally.
- The same rule applies to `bandit` if it found a problem in existing code untouched by the task: a separate commit `[manual] fix(security): <description in English>` before the main work.
- Do not ask the participant "separate commit or mix it in" — the project rule is unambiguous: **do not mix**. Ask only if it is unclear which exact version to bump to or if the fix breaks tests.

## Link to the full standard

The full development standard with examples and numbered paragraphs is in `.agents/agents/python-standards.md`. When you need to reference a specific rule in chat / in a PR comment / in a code review report — use the `§N` format (e.g. `§3 — exception handling`, `§5 — async rules`).
