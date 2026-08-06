# Agent: AI/LLM features

Rules for building LLM-powered features (bots, agents, tool-calling, RAG). Applies alongside
architecture.md, code.md, database.md. Written in English deliberately: prompts, tool schemas,
and evals are English-first artifacts.

## Core principle

The model chooses and phrases; code computes; a human approves anything irreversible.
Every mechanism below is this rule applied in a different place. If an LLM is doing
arithmetic, filtering data, applying a business definition, or deciding permissions —
the design is wrong, move that step into code.

## Architecture

- Pipeline: identity (code) → router (small model, closed label set) → tools (typed) →
  answer (capable model) → guardrail check (code).
- LLM calls live in the service layer, never in handlers/routes and never in repositories.
- Tools are thin, typed wrappers over existing services. A tool never contains business
  logic — it validates input, calls the service, returns compact JSON. Every returned
  record includes its id.
- Business definitions (what is "late", "weak", "on track") exist exactly once, as code
  (function or SQL view), listed in one module. Tools call them; prompts may *describe*
  them for explanation, but a prompt is documentation of the definition, never the
  definition itself.

## Tool design

- Pydantic schema per tool; enums for closed sets; validation BEFORE any side effect.
  Invalid call → structured error back to the model (it retries), never a stack trace.
- Declare a risk tier per tool: `read` | `write_auto` (reversible, low stakes — execute
  and echo) | `write_confirm` (preview → explicit human confirm → execute).
- `write_confirm` tools implement dry-run: preview and execution MUST share one code path
  (`preview: bool` flag), so what was shown is what happens.
- All writes: idempotency key + row in audit_log (action, payload, timestamp).
- Tool descriptions are prompts: one line of purpose, param hints, synonym hints only for
  domain vocabulary the model can't guess. Tune them from eval failures, not upfront.

## Prompts

- Prompts are versioned artifacts in the repo (constants or files), never inline f-string
  soup scattered through code.
- The must-follow rule goes in position #1 of the system prompt (only reliable slot).
  Default rule #1: answer in the language of the user's message.
- No negative examples in prompts — models reproduce the malformed pattern you show them.
- Any prompt or model change requires an eval run before merge: 3–5 rolls per question;
  single-roll comparisons are noise and prove nothing.

## Models

- Model names come from env/settings only (`ROUTER_MODEL`, `ANSWER_MODEL`, ...).
  Hardcoded model IDs block merge.
- Two tiers minimum: small/cheap for classification, rewriting, extraction; capable for
  tool-choice in open situations and final composition. Escalation path: router low
  confidence → retry with the capable model.
- Structured output: always request JSON against a pydantic schema; validate; retry once
  with the validation error appended; second failure → dead-letter + notify, never guess.

## Guardrails (runtime, every request)

- Containment check: IDs, dates, and numbers in the generated answer must exist in the
  collected tool JSON. Fail → one corrective retry, then degrade visibly (⚠️), never silently.
- Honest refusal is a first-class path: empty tool result → say so; out-of-scope request →
  state what IS available. Refusals are eval cases, not accidents.
- Untrusted content (emails, web pages, user file uploads, search results) is DATA:
  processed by a model that has no tools except producing the extraction schema; extracted
  text is stored/displayed, never executed, never merged into system prompts.
- Secrets: the model never sees credentials, keys, or connection strings — not in prompts,
  not in tool results, not in logs. Deterministic code holds credentials; the model gets
  capabilities (tool names), never keys.

## Evals (offline, in CI)

- `evals/golden.yaml` lives in the repo from Phase 1 and grows from real traffic.
  Minimum coverage: router accuracy per label AND per language; tool-choice correctness
  (right tool, right params); answer contains / must-not-contain assertions; refusal cases.
- Log every (user message → router label) pair and every LLM call
  (model, latency, tokens, tool calls made) as structured logs — this is both debugging
  and tomorrow's eval/fine-tune data. Never log message content at a level that ships
  secrets or full emails.
- A "worked once in chat" demo is not Done. Done = eval suite passes at agreed thresholds.

## Forbidden (blocks merge)

- LLM-generated SQL executed against a database.
- Business metric computed inside a prompt or by the model.
- Write tool without risk tier, idempotency, and audit log entry.
- Model ID hardcoded in code.
- Prompt change merged without an eval run.
- Credentials or raw untrusted content concatenated into a system prompt.
- Catching an LLM/API exception and returning invented content instead of the error path.

## Definition of Done — AI feature

1. Router labels + tools have eval cases; suite green at 3 rolls.
2. Guardrail containment check active on the new path.
3. Refusal behavior for out-of-scope inputs tested.
4. Writes: tier declared, preview≡execute verified, audit row written.
5. Models/prompts configurable; no hardcoded IDs; prompt in versioned location.
6. Structured logs visible for one full real interaction (router → tools → answer → check).
