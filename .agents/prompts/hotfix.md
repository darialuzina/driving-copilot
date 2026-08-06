# Hotfix

Urgent fix to production. Minimal scope — only what the fix requires.

---

## Variant A — submodule in a project (`.agents/`)

```text
Jira: <JIRA-KEY>
Incident: <what broke in production, how it manifests>
Branch hotfix/<JIRA-KEY>-<slug> off main. Follow .agents/skills/hotfix.md.

DONE: minimal scope; regression in the same commit; gate from the skill; [agent] commit.
```

---

## Variant B — running directly from ai-sdlc-rules

```text
Jira: <JIRA-KEY>
Incident: <what broke in production, how it manifests>
Branch hotfix/<JIRA-KEY>-<slug> off main. Follow skills/hotfix.md.

DONE: minimal scope; regression in the same commit; gate from the skill; [agent] commit.
```
