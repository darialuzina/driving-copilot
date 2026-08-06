# Commit

One prompt for any task type — feature, bugfix, hotfix, refactor.

**Message format**:

- Prefix — `[agent]` / `[assisted]` / `[manual]` (English marker).
- Conventional Commits tag — `feat:` / `fix:` / `refactor:` / `chore:` / `docs:` / `test:` / `perf:` (English).
- Scope in parentheses, e.g. `(api)`, `(services)`, `(deps)` — English.
- **The description after the colon — in English.**

Example: `[agent] feat(api): add PATCH /links/{id} endpoint`

---

## Variant A — submodule in a project (`.agents/`)

```text
Make a single git commit of the current changes.
Rules from .agents/AGENTS.md: prefix [agent] / [assisted] / [manual],
then Conventional Commits (feat: / fix: / refactor: / chore:).
The description after the colon — in English.

Order:
1. git diff — see what changed.
2. git add <the needed files> — do not add anything extra.
3. git commit -m "[agent] <type>(<scope>): <description in English>"
4. git log -1 --stat — show the result.

If the pre-commit hook failed with an autofix (ruff format, trailing-whitespace):
git add <the fixed files> && git commit again.
If the hook failed with a real error — fix it, do not bypass the hook.
```

---

## Variant B — running directly from ai-sdlc-rules

```text
Make a single git commit of the current changes in the project <repository path>.
Rules from AGENTS.md: prefix [agent] / [assisted] / [manual],
then Conventional Commits (feat: / fix: / refactor: / chore:).
The description after the colon — in English.

Order:
1. git diff — see what changed.
2. git add <the needed files> — do not add anything extra.
3. git commit -m "[agent] <type>(<scope>): <description in English>"
4. git log -1 --stat — show the result.

If the pre-commit hook failed with an autofix (ruff format, trailing-whitespace):
git add <the fixed files> && git commit again.
If the hook failed with a real error — fix it, do not bypass the hook.
```
