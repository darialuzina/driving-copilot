# Unit tests

---

## Variant A — submodule in a project (`.agents/`)

```text
Branch test/<slug>-unit (main clean, otherwise STOP).
Unit tests for <service file>: <scenarios>. Follow .agents/skills/tests-unit.md.

DONE: 100% module coverage; gate from the skill; reviews/<slug>-coverage.md; [agent] commit.
```

---

## Variant B — running directly from ai-sdlc-rules

```text
Branch test/<slug>-unit (clean tree, otherwise STOP).
Unit tests for <service file>: <scenarios>. Follow skills/tests-unit.md.

DONE: 100% module coverage; gate from the skill; reviews/<slug>-coverage.md; [agent] commit.
```
