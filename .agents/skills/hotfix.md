# Skill: Hotfix

## Urgent-fix algorithm

> A hotfix goes to production urgently — **scope discipline is mandatory**. Before
> coding, briefly record for yourself and the operator (in a single chat
> message, not a separate file): what broke in production, what the minimal
> fix is (≤ 20 lines), what we do NOT touch "while we're at it", and how to roll
> back if things get worse. This is not an approval gate — it is insurance
> against scope creep, which costs the most in a hotfix. If you want to think
> before coding — use the AI IDE's Plan mode.

### 1. Preparation
- Read `.agents/agents/hotfix.md` — it contains the strict hotfix rules.
- Create a branch off `main`: `git checkout main && git checkout -b hotfix/<JIRA-KEY>-<short-description>`.

### 2. Minimal fix
- Only one change — the one that eliminates the problem.
- No refactoring, no "while we're at it".
- If the fix requires more than 20 lines — it is not a hotfix but a regular bugfix. Stop and agree the task-type change with the operator; do not let the hotfix sprawl.

### 3. Regression test
- Write a test that reproduces the problem.
- Make sure the test is green after the fix.

### 4. Verify
- `uv run ruff format .` — auto-formatting.
- `uv run ruff check --fix .` — auto-fix the auto-fixable rules.
- `uv run ruff check .` — must be green.
- `uv run basedpyright`
- `uv run pytest -q`
- `uv run pre-commit run --all-files` — run all hooks before committing. Especially important in a hotfix: a red pre-commit = a problem shipping to production.

If anything fails — `.agents/agents/error-handling.md`; the default severity for a
hotfix is High (and if something that was green before your changes now fails —
Critical: stop and call the operator).

### 5. Commit
- `[agent] hotfix(<scope>): <description in English>` — strictly one commit. Tag, scope, and description are all in English.

### 6. At the end of the task
"Hotfix `PROJ-XXX` ready, regression test added, everything green, commit
made. Create the MR to `main`?". Then proceed based on the operator's answer.
