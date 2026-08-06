# AGENTS

You are working in a Python backend project built on FastAPI.

## Core rules

1. Read this file first, plus the relevant topic files from `.agents/`.
2. **On any error — Identify → Assess → Communicate → Solutions.** Do not offer
   a workaround right away — first understand why it failed. Severity levels and
   the response algorithm are in `.agents/agents/error-handling.md`.
3. Do not change the project architecture without an explicit reason.
4. Every change must be minimally sufficient.
5. Every code change must be accompanied by these checks:
   - `uv run ruff check .`
   - `uv run basedpyright`
   - `uv run pytest -q`
6. For schema and DB changes, read `.agents/agents/database.md`.
7. If the public API changes, update the tests and the README.
8. Before preparing an MR, read `.agents/agents/mr.md`.
9. For a hotfix, you must read `.agents/agents/hotfix.md`.
10. Every bug must get a regression test.
11. Do not add dependencies unless necessary.
12. Before starting work, create a branch following the project's branch naming rule.
13. Architectural decisions with ≥ 2 alternatives and an expensive rollback must be
    written up as an ADR with options analysis (see `.agents/agents/docs.md`, the "ADR-full" section).
14. If the task is data-engineering (ETL, Airflow DAGs, Kafka workers, ClickHouse,
    exports to S3) — read `.agents/agents/data-engineering.md`.

## How to work

Agent behavior is driven by **rules** (`.agents/`) and **algorithms**
(`.agents/skills/`). It is a pipeline: a task arrives → the agent reads the relevant skill →
executes the steps → checks → commit. A separate "plan in chat waiting for OK"
is not required — `.agents/skills/*.md` already contains the step-by-step algorithm.

If the task is complex and you want to scout before writing code:

- **Use the built-in Plan mode** of the AI IDE (in Claude Code, Cursor, Continue,
  Codex CLI). In this mode the agent only reads files and describes what it
  intends to do; it does not write or run commands. This is faster and cheaper
  than emulating it via "show the plan in chat, wait for confirmation".
- **Task artifacts** (notes, code review reports, ADRs, intermediate
  results) can be stored in `Tasks/<JIRA-KEY>/` next to the code, so that
  when returning to the task a day later you can see where you left off. This
  is an optional pattern, not a mandatory "always write a plan in md".
- **An architecture document** for a large task (≥ 1 day of work, several
  modules, breaking change) is a separate genre — see `.agents/skills/architecture.md`.
  It is not an "approval gate"; it is a working artifact with C1+C2 diagrams and
  a task list T1-TN.

At the end of the task — a short report to the operator with the result and a
proposed next step. No formalities. The operator's simple reply ("fine, open the
MR" / "hold on, redo X") determines what happens next.

## Branch naming rules

Branches must be named according to the task type and the Jira key.

Branch format:

`<type>/<JIRA-KEY>-<short-description>`

Where:
- `type` — task type: `feature`, `bugfix`, `hotfix`
- `JIRA-KEY` — the task identifier in Jira, e.g. `PROJ-123`
- `short-description` — a short description in `kebab-case`

Examples:
- `feature/PROJ-123-add-link-archive`
- `bugfix/PROJ-456-fix-empty-title-validation`
- `hotfix/PROJ-789-fix-production-db-timeout`

Rules:
- use Latin letters, digits, `/`, and hyphens;
- no spaces;
- no long descriptions;
- for Jira tasks, always include the Jira key in the branch name;
- the branch type must match the task type.

## Commit rules and measuring the agent's contribution

Every commit must be tagged at the start of the message:

- `[agent]` — the agent's diff was accepted without substantial edits (spot fixes to names/formatting are allowed)
- `[assisted]` — the agent did the groundwork, but you rewrote a significant part (logic, structure, >20% of lines)
- `[manual]` — the code was written by hand with no agent involvement

Three tags instead of two are needed because a binary "agent / not agent" split lies in the agent's favor: a commit where you took the idea from the diff and rewrote half of it is more honestly counted as `[assisted]`, not `[agent]`. This matches industry practice: self-reported "AI-assisted" is usually ~40%, but genuinely AI-authored (unedited) is around 27%.

Format — Conventional Commits, tags in English (`feat:`/`fix:`/`refactor:`/`chore:`), **and the description after the colon in English too**.

Examples:
```
[agent] feat(api): add PATCH /links/{id} endpoint and tests
[assisted] refactor(services): rework the service layer after the agent's draft
[manual] docs(readme): fix a typo
[agent] test(links): add regression test for title validation with whitespace
[manual] chore(deps): bump pytest to >=9.0.3 for CVE-2025-71176
```

After completing each task, output a summary block:

```
[agent | assisted | manual] <short task description in English>
Files: <number of files changed>
Tests: <added/changed>
Checks: ruff ✅  basedpyright ✅  pytest ✅
```

## What to do when `git commit` fails on a pre-commit hook

This repository has pre-commit hooks installed (ruff, basedpyright, bandit, pip-audit, gitleaks, end-of-file-fixer, trailing-whitespace, etc.). Every `git commit` runs them **before** the commit is created. Three outcomes are possible:

### Outcome A: All hooks `Passed` — the commit was created

Nothing to do. Show `git log -1 --stat` as confirmation.

### Outcome B: A hook **auto-fixed** files (`files were modified by this hook`)

This is how `end-of-file-fixer`, `trailing-whitespace`, `ruff format`, `ruff check --fix` work. They fix the files **themselves** and signal that the commit must be repeated.

Actions:
1. See which files changed: `git status`.
2. `git add` those files.
3. `git commit -m "..."` again with the same message.

On the second pass the auto-fixes are already applied — the hook will report `Passed`.

### Outcome C: A hook found a **real error** (e.g. `basedpyright` or `bandit`)

This is **not** an auto-fix — it is an error you must understand and fix. Actions:

1. Read the hook's output. Every error has a file path, a line number, and a description.
2. Open the file and work out what is wrong:
   - **basedpyright**: most often a missing type annotation, or `Any` where a concrete type belongs, or accessing `None` without a check. Add the annotation or `# pyright: ignore[<ruleId>]` with a comment explaining **why** that specific ignore is justified.
   - **bandit**: it found an unsafe construct (`subprocess(shell=True)`, `yaml.load` without `SafeLoader`, etc.). Rewrite it as the safe variant. Do not use `# nosec` without an explanation.
   - **pip-audit**: a CVE in a dependency. If your code added that dependency — bump it to the fix version **in a separate commit** (`[manual] chore(deps): bump <package> for CVE-XXXX`). If the CVE is in someone else's dependency you did not touch — see `.agents/agents/security.md`, the "pip-audit" section.
3. Fix, stage (`git add`), commit again.
4. If the hook fails 3 times in a row on the same thing — stop, describe to the user exactly what the error says and what the conflict is. Do not loop.

The extended algorithm for reacting to any errors (not just pre-commit) is in
`.agents/agents/error-handling.md` (severity Critical/High/Medium/Low + the
"Identify → Assess → Communicate → Solutions" rule).

### What is **forbidden**

- **`git commit --no-verify`** — bypassing all hooks, **never**.
- **`SKIP=hook git commit ...`** — skipping specific hooks, **never**.
- **`PRE_COMMIT_ALLOW_NO_CONFIG=1`** — this fires when `.pre-commit-config.yaml` is missing. If you saw this variable in git's hint — the config is **lost**; restore it (`git show HEAD:.pre-commit-config.yaml > .pre-commit-config.yaml`), do not bypass.

Details — in `.agents/agents/security.md`, section "Pre-commit hooks — no bypassing".

## Converting documentation to Confluence Wiki Markup

If you need to convert a `.md` file to Confluence Wiki Markup for pasting via `Other macros → Markup → Confluence wiki`:

Caveat: the Markup-macro path is only available in the legacy Confluence editor, which is deprecated as of 2026-04-01; the new cloud editor does not have this macro.

**Read the rules file before converting:**
```
.agents/md-to-confluence-rules.md
```

The file lives at the root of `.agents/` (one level above `.agents/agents/`).

It contains:
- the exact bash commands for the conversion (pandoc + sed + clean-jira-escapes.py)
- a table of typical errors and their fixes
- a result-verification script (three checks must return 0)
- the folder structure for the finished `.txt` files

**Rule:** never convert by hand and never invent rules on the fly — everything is in `md-to-confluence-rules.md`.
