# Error handling rules

What to do when an error, ambiguity, or blocker arises at any step of a
task. This file applies to every skill in
`.agents/skills/` — feature, bugfix, refactoring, hotfix, code-review,
tests, docs.

## The main rule

**Do not offer a workaround right away — first understand why it failed.**

The habit of slapping on `# type: ignore`, `try/except: pass`, `# noqa`, or
rewriting a test to match current behavior turns the problem into
tech debt with a delayed explosion. For every error, go through 5 steps in
order:

1. **Identify** — state clearly **what exactly** broke. Not "basedpyright
   is complaining", but "basedpyright says
   `services/link.py:42` returns `Link | None`, but the handler
   expects `Link`".
2. **Assess impact** — what severity (Critical / High / Medium / Low,
   table below), what it blocks and what it does not.
3. **Communicate** — tell the operator what happened and what their options
   are. Do not choose for them on serious severities.
4. **Offer solutions** — concrete recovery steps, not vague
   phrases like "I'll try to fix it".
5. **Document** — record whatever was chosen: either as a comment in the code
   next to the compromise (`# accepted compromise: <what>, reason: <why>`),
   or as a short note in `Tasks/<key>/decisions.md` (if the task folder is
   used). The goal: when returning to the code a month later, it is clear
   why it is this way.

## Severity levels

| Level | Means | Response |
|---|---|---|
| **Critical** | Further work is impossible. Something you did not touch broke, or the code cannot be compiled/run at all. | Stop working. Record the symptom and the context. **Do not offer a workaround**. Wait for the operator's explicit decision. |
| **High** | The current step will not finish as planned. E.g. a test fails for a non-obvious reason, basedpyright shows an error you cannot explain. | Describe the problem, offer 2–3 recovery options with trade-offs, get the operator's choice. Do not move forward silently. |
| **Medium** | The step can be closed with a workaround, but it is a compromise that must be explicitly recorded. E.g. you could not reuse an existing helper and had to write a local copy. | Describe the workaround, mark it in the plan as "accepted compromise — `<what>`, reason — `<why>`". Move on. |
| **Low** | Minor, non-blocking. E.g. a typo in a comment in a file you are not touching. | Record it in the plan as a `TODO` (as a separate item or in an existing one); do not get distracted in this task. |

## Typical situations

### `basedpyright` shows an error in code you did not touch

Default severity — **High**. It means either you broke something
indirectly (changed a type in one place and it broke in another), or
basedpyright was updated and caught a previously missed error.

- ❌ **Do NOT add** `# pyright: ignore[...]` or `# type: ignore` without explanation just to keep going.
- ✅ **Do:** read the error, open the referenced file, work it out.
  If it is a side effect of your changes — fix it. If it is a pre-existing
  problem unrelated to the task — record it as a separate
  `[manual] fix(types): <description in English>` commit before the main work (see the rule on
  pip-audit / bandit in `.agents/agents/code.md`).

### A test fails for a non-obvious reason

Severity — **High**.

- 1st attempt: read the traceback carefully, check your assumptions.
- 2nd attempt: add `print`/`breakpoint` (temporarily — remove before committing!), inspect the state.
- 3rd attempt: if it is still unclear — **stop**. Describe to the operator exactly what is unclear, what the traceback is, and what you have already tried. Do not slap on `pytest.skip` or bend the asserts.

The **three attempts** rule is the same as for pre-commit in `.agents/AGENTS.md`.
The "try the same thing again" loop is an anti-pattern.

### A migration failed / Alembic conflict

Severity — **Critical** if the conflict is in `head` or downgrade is broken.
**High** in all other cases.

- Do not run `alembic stamp head` without understanding the state — it
  leaves the DB in an inconsistent state.
- Show the operator `alembic history --verbose` and `alembic current`, describe
  what you see, let them choose the migration merge strategy.

### `pre-commit` failed on a hook that used to pass

Severity depends on the hook:

- **ruff / basedpyright** on your changes — High, fix it (see
  `.agents/AGENTS.md` Outcome C).
- **bandit / pip-audit** on code you did not touch — High, a separate
  commit `[manual] fix(security|deps): <description in English>` before the main work (tag, scope, and description all in English).
- **gitleaks** — **Critical**. Stop immediately, do not try to
  bypass it. If a secret really got into the diff — revoke the secret itself at
  its source (revoke the API key / rotate the password), then remove it from
  the code. If it is a false positive — add it to `.gitleaksignore` with
  an explicit justification in a comment.

### The architecture document in `Tasks/<key>/<key>-architecture.md` contradicts the code

Severity — **High** (if the code is already merged) or **Medium** (if the code
is still on your branch).

- Do not write code "per the plan" while ignoring reality.
- Do not fix the code "per the plan" and break behavior.
- Update the plan to the real state, explain the discrepancy to the operator,
  and ask: do we redo the code or update the plan as the source of truth.

### A third-party library does not behave as documented

Severity — **High**.

- Do not assume you misread the documentation. Show the
  operator a minimal reproducible example (5–10 lines), expected
  vs actual behavior, and the library version.
- A workaround in code that hides the problem — only if the operator explicitly
  approved it. Mark in the plan "accepted compromise due to `<lib> <version>`,
  TODO: remove after `<condition>`".

### The session context is filling up and you start forgetting earlier decisions

Severity — **High** (for the quality of the work itself).

- **Stop**; do not "squeeze out a little more".
- Record the current progress in a short note — either in chat to the operator,
  or in `Tasks/<key>/session-state.md` (if the task folder is used).
  What is needed: what is already done, which file/line you stopped at, which
  decision must be made next.
- Tell the operator: "Context is close to overflowing, state is recorded.
  I suggest continuing in a new session from this point."

## What NOT to do at any severity

- **Silently apply a workaround** (`# noqa`, `# type: ignore`, `pytest.skip`, a bare `except: pass`) — that turns a visible problem into a hidden one.
- **Change a test to match current behavior** — a test verifies the requirement, not the implementation. If the test fails and the code's behavior is in fact correct — the test must be rewritten deliberately, with explicit agreement that the requirement changed.
- **Defer to `TODO` anything that is not Low** — Low severity is "a typo in a comment in someone else's file", not "could not figure out why the migration failed".
- **Loop on one error for more than 3 attempts.** After the 3rd — stop and escalate to the operator.
- **Do "fixed it, let's see"** without understanding why the previous version did not work. If you do not understand why it did not work — you do not understand why it works now.
