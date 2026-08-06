# Architecture document

Prompt for writing an architecture plan **before** implementation starts.

---

## Variant A — submodule in a project (`.agents/`)

```text
Jira: <JIRA-KEY>
Task: <one-line description>

Read .agents/AGENTS.md, .agents/agents/architecture.md, .agents/skills/architecture.md.

Study the project codebase: repository structure, existing services,
base classes and patterns, Settings, extension points.

Write the architecture document following the algorithm in .agents/skills/architecture.md —
follow the skill without duplicating its rules.
Save it to Tasks/<JIRA-KEY>/<JIRA-KEY>-architecture.md.
If you find a contradiction or missing information — ask, do not guess.
```

---

## Variant B — running directly from ai-sdlc-rules

```text
Jira: <JIRA-KEY>
Task: <one-line description>
Project: <repository path or description>

Read AGENTS.md, agents/architecture.md, skills/architecture.md.

Study the project codebase at the given path: structure, existing services,
base classes and patterns, Settings, extension points.

Write the architecture document following the algorithm in skills/architecture.md —
follow the skill without duplicating its rules.
Save it to <path>/Tasks/<JIRA-KEY>/<JIRA-KEY>-architecture.md.
If you find a contradiction or missing information — ask, do not guess.
```
