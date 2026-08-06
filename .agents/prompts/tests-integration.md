# Integration tests

---

## Variant A — submodule in a project (`.agents/`)

```text
Branch test/<slug>-integration (main clean, otherwise STOP).
Integration tests for <endpoints/scenarios>. Follow .agents/skills/tests-integration.md.

DONE: gate from the skill; 100% coverage of the scope; reviews/<slug>-coverage.md; [agent] commit.
```

---

## Variant B — running directly from ai-sdlc-rules

```text
Branch test/<slug>-integration (clean tree, otherwise STOP).
Integration tests for <endpoints/scenarios>. Follow skills/tests-integration.md.

DONE: gate from the skill; 100% coverage of the scope; reviews/<slug>-coverage.md; [agent] commit.
```
