# Orchestrating Coder → Reviewer → Summarizer

## Variant A — submodule in a project (`.agents/`)

```text
Task: <one line>
Follow .agents/skills/orchestrate-coder-reviewer-summarizer.md.
Role models — from the table in the skill. Do everything yourself. Do not git push / PR.
final_gate_council=false.
Summarizer: claim_ledger (every bullet → evidence_span in the file).
```

## Variant B — running from ai-sdlc-rules

```text
Task: <one line>
Follow skills/orchestrate-coder-reviewer-summarizer.md.
Role models — from the table in the skill. Do everything yourself. Do not git push / PR.
final_gate_council=false.
Summarizer: claim_ledger (every bullet → evidence_span in the file).
```
