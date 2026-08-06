# Skill: Feature

## Algorithm for a new-feature task

> If you want to think the solution through **before** writing code — switch the
> AI IDE into **Plan mode** (Claude Code, Cursor, Continue, Codex). In this mode
> the agent only reads and describes what it will do, without writing. Return to
> Agent mode once the approach looks good. Task artifacts (notes, ADRs, review
> reports) can optionally go into `Tasks/<JIRA-KEY>/`.

### 1. Preparation
- Clarify the goal of the change — what exactly should appear in the API.
- Find the Jira ticket and create a branch: `git checkout -b feature/<JIRA-KEY>-<short-description>`.
- Read `.agents/agents/architecture.md` — understand which layer the change belongs to.

### 2. Study the codebase
- Find the existing extension points in the code.
- Determine which layers are affected: domain, db, service, api.
- Check whether a similar feature exists — do not duplicate logic.

### 3. Implementation by layers (strictly in this order)
1. **domain/** — add or extend a value object / entity / domain error.
2. **db/models.py** — add fields to the SQLAlchemy model if needed.
3. **repositories/link_repository.py** — add a repository method (+ ORM ↔ domain mapping).
4. **services/** — implement the business logic.
5. **api/** — add the endpoint.
6. If the DB schema changed — create an Alembic migration.

### 4. Tests
- Unit tests for the service layer (Fake repository).
- Integration tests for the API (`httpx.AsyncClient` + a real DB).

### 5. Final check
- `uv run ruff format .` — auto-formatting.
- `uv run ruff check --fix .` — auto-fix import sorting (`I001`), unused imports (`F401`), and other auto-fixable rules. Run it **before** `ruff check`.
- `uv run ruff check .` — must be green. If not — the rule is not auto-fixable, fix by hand.
- `uv run basedpyright`
- `uv run pytest -q`
- `uv run pre-commit run --all-files` — run all hooks (ruff, basedpyright, bandit, pip-audit) before committing. If a hook fails — fix and rerun. Never commit with a red pre-commit.

If anything fails in a non-trivial way at any step — follow the algorithm in
`.agents/agents/error-handling.md` (Identify → Assess → Communicate →
Solutions); do not slap on a workaround right away.

### 6. Commit
- `[agent] feat(<scope>): <description in English>` — one commit per feature. Tag, scope, and description are all in English.

### 7. At the end of the task
Report briefly and ask what is next. No formal gate — just
"Task `PROJ-XXX` done, everything green, commit made. Moving on — should I create
the MR, or are there changes?". The operator's answer determines the next steps.
