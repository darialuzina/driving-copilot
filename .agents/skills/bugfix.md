# Skill: Bugfix

## Bug-fixing algorithm

> If the root cause is not obvious — switch the AI IDE into **Plan mode** and
> scout the context before writing the regression test. Do not guess where
> the fix goes. If the recon shows that the symptom and the actual cause are
> in different places — that is normal; note it and continue.

### 1. Preparation
- Reproduce the problem — understand exactly what is broken.
- Create a branch: `git checkout -b bugfix/<JIRA-KEY>-<short-description>`.

### 2. Locate the defect
- Find the file and line where the error occurs.
- Understand the root cause, not the symptom.
- If something significant surfaces along the way (the root cause is not where
  you expected, the scope is wider than it seemed) — tell the operator before
  continuing. Do not stay silent.

### 3. Test first
- Write a regression test that **fails** before the fix.
- Make sure the test actually reproduces the bug: `uv run pytest -q` — must FAIL.

### 4. Minimal fix
- Fix only the root cause — do not refactor along the way.
- Do not change the public API unless the fix requires it.

### 5. Verify
- `uv run pytest -q` — the regression test is now green.
- `uv run ruff format .` — auto-formatting.
- `uv run ruff check --fix .` — auto-fix the auto-fixable rules (`I001`, `F401`, etc.).
- `uv run ruff check .` — must be green.
- `uv run basedpyright`
- `uv run pre-commit run --all-files` — run all hooks before committing. If a hook fails — fix and rerun.

If something fails in a non-trivial way (basedpyright complains about code you
did not touch; a test fails for an unclear reason) — follow
`.agents/agents/error-handling.md`; do not slap on `# type: ignore` without understanding.

### 6. Commit
- `[agent] fix(<scope>): <bug description in English>` — one commit. Tag, scope, and description are all in English.

### 7. At the end of the task
Briefly: "Bug `PROJ-XXX` fixed, regression test added, everything green.
Create the MR, or are there changes?". Then proceed based on the operator's answer.
