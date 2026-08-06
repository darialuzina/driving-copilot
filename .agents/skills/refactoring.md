# Skill: Refactoring

## Algorithm for a refactoring task

> Refactoring is the type of task with the "widest blast radius": one rename
> can touch dozens of files. Before coding, **always** collect the full list
> of occurrences via `grep -r "OldName" app/ tests/` and scan it with your
> eyes. If even one file looks unexpected — figure it out before editing.
> The AI IDE's **Plan mode** is convenient for the recon. The artifact
> "file list + list of replacements by layer" can optionally go into
> `Tasks/<JIRA-KEY>/` — useful when restarting the session.

### 1. Preparation

- Read `.agents/agents/refactoring.md`.
- Read `.agents/agents/architecture.md` — make sure you understand the layers.
- Verify that the tests are green: `uv run pytest -q`.
- Create a branch: `git checkout -b refactor/<JIRA-KEY>-<short-description>`.

### 2. Study the codebase before editing

Before changing a single line — find all usage points:

```bash
grep -r "OldName" app/ tests/ --include="*.py" -l
```

Compile the list of all files to change. If even one file is
unexpected — figure out why it is there before continuing.

### 3. Changes by layers (strictly in this order)

**3.1 — domain/**
- Rename the dataclass / TypeAlias / constant.
- Update type annotations inside the module.
- Verify: `uv run ruff check . && uv run basedpyright`.

**3.2 — db/models.py**
- Update the SQLAlchemy model (the class, `__tablename__` only if the table name changes).
- If the table name changes — create an Alembic migration:
  ```bash
  uv run alembic revision --autogenerate -m "rename short_link to link"
  uv run alembic upgrade head
  ```
- Verify: `uv run ruff check . && uv run basedpyright`.

**3.3 — repositories/link_repository.py**
- Update imports, type annotations, and method names if they contained the old name.
- Verify: `uv run ruff check . && uv run basedpyright`.

**3.4 — services/**
- Update imports and type annotations.
- Service method names — only if they contained the old name (`create_short_link` → `create_link`).
- Verify: `uv run ruff check . && uv run basedpyright`.

**3.5 — api/**
- Update imports, DTO classes, type annotations.
- Do not change endpoint URL paths unless the task says so explicitly.
- Verify: `uv run ruff check . && uv run basedpyright`.

**3.6 — tests/**
- Unit tests: update imports, Fake class names, type annotations.
- Integration tests: update imports, annotations.
- Run all tests: `uv run pytest -q`.

### 4. Final check

```bash
grep -r "OldName" app/ tests/ --include="*.py"
```

The output must be empty.

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
uv run pre-commit run --all-files
```

All four — green. If `pre-commit` caught something the previous steps did not see (e.g. `bandit` or `pip-audit`) — fix and rerun.

### 5. Commit

```bash
git add -p
git commit -m "[agent] refactor(<scope>): rename OldName → NewName across all layers"
```

Tag, scope, and description are all in English.

### 6. At the end of the task

"Refactoring done, all layers updated, tests green, `grep OldName`
is empty, commit made. Moving on — MR, or are there changes?". Then proceed
based on the operator's answer.

## What to do if a test fails

1. Read the error — most likely an `ImportError` or `AttributeError` due to a missed rename.
2. `grep -r "OldName" app/ tests/` — find what you missed.
3. Fix only that spot, run the tests again.

If the test fails on the same thing 3 attempts in a row — stop and follow
`.agents/agents/error-handling.md` (this is already High severity — do not slap
on a workaround; dig into the root cause).

## What to do if basedpyright complains

The typical error is an import of the old name in another file:

```
error: "OldName" is not exported from "app.domain.task"
```

Find the file, update the import. Do not add `# type: ignore` — that hides the problem.
