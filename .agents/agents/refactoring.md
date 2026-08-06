# Refactoring rules

## When refactoring is appropriate

- Renaming domain concepts when the old name is misleading.
- Extracting duplicated logic into a service or helper.
- Splitting an overgrown module into several with clear responsibilities.
- Changing layer ownership — e.g. moving validation from the API into the service.

## When refactoring is forbidden

- Without an explicit task — don't rename things "while you're at it".
- In a hotfix branch — only the minimal fix.
- If there are no tests covering the code being changed — tests first, then refactoring.

## Mandatory steps before starting

1. Make sure all tests pass before refactoring: `uv run pytest -q`.
2. Capture the current state: `git status` — the working tree must be clean.
3. Create a branch following the rule `refactor/<JIRA-KEY>-<short-description>`.
4. Find all usage sites before making edits: `grep -r "OldName" app/ tests/`.

## Order of changes

Refactoring must proceed layer by layer — top-down along the dependencies:

```
domain/       ← start here (no dependencies on other layers)
db/models     ← SQLAlchemy model
repositories/link_repository ← repository methods (ORM ↔ domain mapping)
services/     ← service layer
api/          ← HTTP layer
tests/        ← last (both unit and integration)
alembic/      ← only if the DB schema changes
```

Changes to tests — only after the main code is assembled and the linters pass.

## Mandatory checks after every file

```bash
uv run ruff check .
uv run basedpyright
```

Do not move on to the next file until the current one passes static analysis.

## Mandatory checks at the end

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
```

All three must be green before creating the commit.

## What to verify in the diff

- All occurrences of the old name are replaced — verify with `grep -r "OldName" app/ tests/`.
- The public API of the endpoints has not changed (`/links` paths stay `/links` unless agreed otherwise).
- An Alembic migration is created if the DB schema changed (table name, columns).
- No commented-out code or temporary `# TODO`s left over from the refactoring.
- Imports in every changed file are up to date.

## Commit

One commit per refactoring (unless there is a compelling reason to split):

```
[agent] refactor: rename ShortLink → Link across all layers
```

If the refactoring is large — splitting by layers is acceptable:
```
[agent] refactor: rename ShortLink → Link in the domain and db layers
[agent] refactor: rename ShortLink → Link in the services and api layers
[agent] refactor: update tests after the ShortLink → Link rename
```
