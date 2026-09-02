# Driving Copilot

A Telegram assistant for preparing for the Dutch practical driving exam (CBR, category B). It tracks driving lessons, maps progress against the official CBR skill matrix, answers exam questions with citations from the official *Rijprocedure B*, and runs unattended on a small cloud VM.

The project is also a reference implementation of an agentic assistant built on open-weight models: intent routing, typed tools, a semantic layer, provenance-labeled answers, code-enforced guardrails, an eval set, and access control applied below the model.

---

## What it does

```
User: I had a lesson today with Abid — clutch better, roundabouts better,
      once went 60 where the limit was 50
Bot:  Logged for 2026-08-13 (trial lesson with Abid).
      gear use & clutch control — good · roundabouts — good ·
      speed adaptation — needs attention

User: How are my roundabouts?
Bot:  30 Jul — needs attention ("still difficult"), 6 Aug — needs attention,
      13 Aug — good. Status: in_progress — one more good lesson makes it solid.

User: Can I fail for stalling?
Bot:  A single stall does not normally fail you; frequent stalling can,
      especially during special manoeuvres.
      (Rijprocedure B, §Toepassing Hoofdstuk 1; §3.7)

User: How much does the practical exam cost?
Bot:  from cbr.nl just now: €143,50 in 2026.
```

Capabilities: lesson history and upcoming lessons · logging free-form notes (English or Russian), fuzzy-matched to a 29-skill CBR matrix · gap analysis and pace against an exam date · exam knowledge Q&A over a verbatim knowledge base, with a scoped live-web fallback · recording and cancelling booked lessons. Replies follow the language of the question.

## Architecture

```
Telegram (single allowed chat — identity checked in code before any model call)
      │
      ▼
  Router — small model (qwen3-coder), one call, one label
      │     lookup / analytics / log / docs / smalltalk / other
      │     invalid label → retry with the larger model → safe fallback
      ▼
  Agent loop — larger model (GLM 5.2) + typed tools
      │     Pydantic-validated params, enums, date/tenant checks before the DB
      ▼
  Tools → services → semantic layer → PostgreSQL
      │     skill_status() / pace() / stale(): each definition exists once, in code
      ▼
  Guardrails (code, after generation)
        · containment: ids, dates and numbers in the answer must exist in the
          tool results — otherwise one corrective retry, then a marked send
        · provenance: knowledge answers must carry exactly one source marker
        · language: reply script must match the question's
        · refusal for out-of-scope requests is a tested path
```

The rule applied throughout: the model chooses and phrases; code computes; irreversible actions are gated. The LLM does not write SQL, does not apply business definitions, and never sees credentials.

Design notes:

- **Typed tools with risk tiers.** Reads are unrestricted; writes are idempotent (argument-hash keys) and audit-logged; consequential actions are reserved for a preview→confirm tier.
- **Semantic layer** (`app/services/semantic.py`). "Weak", "solid" and "on track" are functions, not prompt text. A definition changes in one place.
- **Provenance labels, enforced in code.** Every knowledge answer states its source: a Rijprocedure section, "from cbr.nl just now" (Tavily, cbr.nl-scoped — a flow that holds no write tools, since web text is untrusted input), or "general knowledge — verify in your theory book".
- **Verbatim knowledge base.** The official Rijprocedure B PDF is converted to structure-preserving Dutch markdown (297 sections, from the document's own table of contents) and translated section by section with the DeepL API — no LLM in the translation path. Tests enforce fidelity: every heading must exist in the PDF extraction, nl/en length ratios stay within a band, section counts match.
- **Telemetry.** Every LLM call logs model, latency and token usage; router decisions are appended to `logs/router.jsonl` as eval data. Telemetry writes cannot fail a user request.

## How it was built

Spec-driven, with coding agents working under a rules harness:

- [`driving-copilot-spec.md`](driving-copilot-spec.md) — the living specification every agent session reads; deviations flow back into it as "as built" notes.
- `.agents/` — architecture, code and testing rules, plus [`ai.md`](.agents/agents/ai.md) for LLM features (guardrails, prompt discipline, eval requirements, secrets handling). Pre-commit hooks, ruff, basedpyright and pytest enforce what the rules describe.
- Implementation by [OpenCode](https://opencode.ai) running GLM 5.2 against these rules and skills; code review by a second model (Kimi K2.7) — see [`reviews/DRIVE-4-code-review.md`](reviews/).
- [`reviews/DRIVE-2-spec-audit.md`](reviews/) — an agent-written audit of the implementation against the spec, triaged by hand into fixes, spec updates and deferred items.
- `evals/golden.yaml` — router accuracy per label and per language, tool-choice checks, answer assertions, refusal cases; grown from real traffic.

Work is split into reviewable tasks (`DRIVE-1` … `DRIVE-9` in the git log), one branch each: build → review → merge → deploy.

Production issues found in the first days of use, and their fixes:

| Issue | Cause | Fix |
|---|---|---|
| Test suite deleted real data | dev and test shared one database | separate databases, a guard fixture that aborts test runs not pointed at `*_test`, transactional fixtures |
| Bot stopped answering | a telemetry write failed and crashed the handler | telemetry wrapped; rule added: observability failures never break a request |
| Replies in the wrong language | model followed the language of retrieved notes | language detected in code, injected per message, checked on output |
| Finished lesson counted as upcoming | no scheduled→completed transition | logging notes completes the session; data repaired by migration |
| Same-day lesson missing from history | `date < today` boundary | boundary defined once, tests added |

## Stack

Python 3.14 · python-telegram-bot v22 · PostgreSQL, SQLAlchemy, Alembic · structlog · uv. Models via OpenRouter (qwen3-coder for routing, GLM 5.2 for answers), configured by environment variables. DeepL for translation, Tavily for the web fallback.

Deployment: Google Cloud e2-micro (free tier), Docker Compose with bot, Postgres and a nightly `pg_dump` sidecar; migrations run on boot; no inbound ports (long polling). Update is `git pull && docker compose up -d --build`. Operator instructions: [`RUNBOOK.md`](RUNBOOK.md).

## Limitations and roadmap

No conversation memory yet — each message stands alone, and the bot is instructed not to imply otherwise. Pre-lesson and weekly digests and a live eval runner are specified (spec §8, §9) but not built. The skill matrix is configuration and grows from real lessons.

## Running it

Requires a Telegram bot token, an OpenRouter key and optionally DeepL and Tavily keys — see `.env.example`.

```bash
uv sync
docker compose up -d db
uv run alembic upgrade head
uv run python -m app.main backfill   # seed lesson history (idempotent)
uv run python -m app.main            # start the bot
uv run pytest
```
