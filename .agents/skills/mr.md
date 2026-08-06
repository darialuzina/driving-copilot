# Skill: Merge Request

## MR preparation algorithm

### 1. Before creating the MR
- Read `.agents/agents/mr.md` — the formatting requirements.
- Run the auto-fixes: `uv run ruff format . && uv run ruff check --fix .`.
- Make sure all checks pass: `uv run ruff check . && uv run basedpyright && uv run pytest -q`.
- Make sure the branch is up to date: `git fetch origin main && git rebase origin/main`.

### 2. MR description
- Title: type + short description (`feat: add link update endpoint`).
- Body: what changed, why, how to verify.
- Reference the Jira ticket.

### 3. Checklist before submitting
- No commented-out code.
- No debug `print()`.
- No stray files in the commit.
- All new endpoints are covered by tests.
- If the DB schema changed — there is an Alembic migration.
