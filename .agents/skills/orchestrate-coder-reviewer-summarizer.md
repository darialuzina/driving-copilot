# Skill: Orchestrating Coder → Reviewer → Summarizer

This is the AgentPlatform training profile (compact).

## Roles and models (AgentPlatform pins are already in opencode.json)

| Role | Who | Model (id for `--model` / UI) | Permissions | Role skill |
|---|---|---|---|---|
| Orchestrator | state owner | `z-ai/glm-5.2` (current session) | gates, iterations, stop | this file |
| Coder (Developer) | **writes code** + tests | `deepseek/deepseek-v4-pro` | edit + bash in the project | `.agents/skills/feature.md` (or bugfix/refactor) |
| Reviewer | **review** / verdict | `moonshotai/kimi-k2.7-code` | **read-only** | `.agents/skills/code-review.md` |
| Summarizer | PR report + claim ledger | `z-ai/glm-5.2` | **read-only** | tests-* gate + report |

In OpenCode, prefer separate passes:
`opencode run --model agentplatform/<id> "…"`. In a single TUI — switch the model between roles;
do not mix roles in one response. Continue: a new chat + a model switch for each role;
the Orchestrator session only coordinates (or you follow the skill step by step yourself).

## Inviolable rules

1. One state owner — the Orchestrator (counts iterations, runs gates, decides when to stop).
2. Only the Coder changes code. Reviewer/Summarizer are read-only; any worktree change by them = stop.
3. Do not trust self-reports: the Orchestrator runs the commands itself and reads stdout.
4. Summarizer only after `MERGE`. Red CODE_GATE / `CHANGES_REQUESTED` → back to the Coder.
5. Return budgets (default **5** per loop, counted by the Orchestrator):
   - CODE_GATE → Coder ≤ **5**
   - Reviewer → Coder (`CHANGES_REQUESTED`) ≤ **5**
   - Summarizer → Coder (`REWORK`) ≤ **5**
   The Summarizer does not "polish the MERGE": it maintains the **claim ledger**, catches
   hallucinations and hollow Reviewer nitpicks; when in doubt — `REWORK`, not a blind `READY_FOR_PR`.
6. `git push` / opening the PR — do not do it (a separate human step).
7. The opt-in council at FINAL_GATE (`critical` / `final_gate_council`) — **only if explicitly in the task**;
   by default in training practice it is **off**.

## State machine

```text
INIT → CODER → CODE_GATE ─┬─ fail → CODER           (budget ≤5)
                          └─ pass → REVIEWER
                                      ├─ CHANGES_REQUESTED → CODER  (budget ≤5)
                                      ├─ BLOCKED → ESCALATE
                                      └─ MERGE → SUMMARIZER
                                                    ├─ REWORK → CODER  (budget ≤5)
                                                    ├─ BLOCKED → ESCALATE
                                                    └─ READY_FOR_PR
                                                         └─ (opt) council 2/3 on claims
```

## CODE_GATE (run by the Orchestrator)

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
```

Red → back to the Coder with the concrete log (not to the Reviewer), until the CODE_GATE→Coder
budget ≤5 is exhausted. Do not weaken the gate/coverage.

## Handoff (compact, no reasoning)

Coder → `{"changed":[...],"commands":[{"cmd":"...","exit":0}],"risks":[...]}`  
Reviewer → a one-line verdict `MERGE|CHANGES_REQUESTED|BLOCKED` + findings `file:line`
(`CONFIRMED` only with verbatim evidence).  
Summarizer → `READY_FOR_PR` | `REWORK` | `BLOCKED` + **claim_ledger** (mandatory):

```json
{
  "decision": "READY_FOR_PR",
  "changes": ["API returns 410 on LinkExpired"],
  "claim_ledger": [{
    "claim_id": "CLM-001",
    "text": "API returns 410 on LinkExpired",
    "evidence_type": "file",
    "evidence_ref": "app/api/routes.py",
    "evidence_span": "status_code=410",
    "status": "GROUNDED"
  }],
  "rework_reason": null
}
```

Ledger rules (training minimum):

- every bullet in `changes[]` = `claim_ledger[].text` verbatim;
- `READY_FOR_PR` only if all claims are `GROUNDED` and the `evidence_span` exists in the file/log;
- otherwise `decision=REWORK` + a non-empty `rework_reason` (not "a pretty PR");
- artifact on READY: `reviews/orch-<slug>.md` (PR text with a ledger section).

## FINAL_GATE (Orchestrator)

1. Reviewer = `MERGE`; CODE_GATE green after the last change.
2. Summarizer was read-only (the worktree did not change).
3. Every claim's span actually exists in `evidence_ref` (open the file and verify).
4. Opt-in council: only if the task explicitly has `critical=true` or
   `final_gate_council=true` — then a trio of models (as in panel-backends quality)
   votes majority 2/3 **on each claim_id** (`CONFIRMED|REJECT|INCONCLUSIVE`);
   ≥2 REJECT → `REWORK`. Without the flag — do **not** run the council.
5. `git push` / PR — a human.

## How to run (participant)

1. `cd ~/work/ai-python-workshop/fastapi`
2. The agent (GLM 5.2 = Orchestrator) reads **this** skill.
3. The task is a single line (feature/bugfix); for training practice do not enable the council.
4. The Orchestrator drives the loop; the roles run on their models (DeepSeek V4 / Kimi 2.7 / GLM 5.2).
5. You join on `BLOCKED` or `READY_FOR_PR` (with the claim ledger in the report).

## Stop

Any loop's budget exhausted (≤5); the same blocker for two rounds; a read-only role changed code;
the Coder weakened a test/gate; a claim without a span is being submitted as READY; a human product
decision is needed. Save the diff+verdict+ledger and name the next step.
