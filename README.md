# Driving Copilot

A Telegram-based AI copilot for Daria's driving-exam preparation. Tracks lessons
(parsed from On My Way booking emails + quick notes after each lesson), maps progress
against the official CBR exam requirements, and answers questions in chat.

Architecture: small-model router → typed tools → deterministic code → guardrails → evals.
The model chooses and phrases; code computes. Every fact in an answer comes from a tool result.

See `driving-copilot-spec.md` for the full specification.

## Stack

- Python 3.14, async SQLAlchemy 2.0, PostgreSQL (docker-compose), Alembic
- `python-telegram-bot` v22 (async), `openai` client against OpenRouter, `httpx` for Tavily
- Two models via env: `ROUTER_MODEL` (classification) and `ANSWER_MODEL` (tool-calling + answers)
- `TAVILY_API_KEY` for the cbr.nl-scoped live web fallback (`web_search_cbr`)
- `DEEPL_API_KEY` (free tier) for translating the Rijprocedure B KB (build-time only)

## Setup

```bash
uv sync
docker compose up -d db
cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_ID, LLM_API_KEY, TAVILY_API_KEY
alembic upgrade head   # creates tables + seeds the CBR skills matrix
uv run python -m app.main backfill   # load Daria's lesson history (idempotent)
uv run python -m app.main            # run the Telegram bot
```

To find your `ALLOWED_CHAT_ID`: start the bot, send it `/start`, and read the chat id
from the `bot.ignored_no_allowed_chat_id` log line, then set it in `.env` and restart.

## Checks

```bash
uv run ruff check .
uv run basedpyright
uv run pytest -q
```

Phase 2 live smoke (the three provenance label paths against the real LLM + Tavily):

```bash
PYTHONPATH=. uv run python scripts/phase2_live_smoke.py
```

## Deploy

Production runs on a single Google Cloud `e2-micro` (always-free tier) under
docker compose with three services: `db`, `bot`, `backup`. The bot uses long
polling — outbound only, no inbound ports/TLS. Full instructions (provision,
install docker, clone, ship `.env`, `make deploy-check`, `docker compose up
-d`, verify `/start`, update, backup/restore, logs) are in
[`RUNBOOK.md`](RUNBOOK.md).

```bash
make deploy-check   # validate .env keys (names only) + compose config
docker compose up -d --build
```

## Phase 2 (current)

Everything in Phase 1 plus the "brain": the semantic layer (`skill_status`, `pace`,
`stale` — one code definition each per spec §3), the remaining read tools
(`get_skill_progress`, `get_gap_analysis`, `get_notes`, `get_pace`), and the docs
stack. The CBR Rijprocedure B knowledge base is a **verbatim** conversion of the
official CBR PDF (`knowledge/sources/rijprocedure-b.pdf`) into
`knowledge/rijprocedure-b.nl.md` (297 sections, real numbering from the document's
own table of contents) plus a faithful DeepL translation in
`knowledge/rijprocedure-b.en.md`. Agentic navigation is exposed via `get_toc`
(section tree: ids + en/nl titles + real numbers) and `get_section(section_id)`
(verbatim en + nl text); `get_cbr_info` returns verbatim topic excerpts with the
cbr.nl source URL and fetch date; `cbr_search` is keyword search over `knowledge/`;
`web_search_cbr` (Tavily, cbr.nl-scoped) is fallback only, with no write tools in
that flow. Provenance rule #5 is active (KB section citation / "from cbr.nl just
now" / "not from the CBR docs — general knowledge"). Citations use the document's
real section numbers (e.g. "Rijprocedure B, §3.7"). Analytics and docs route
through the agent loop (the Phase 1 `PHASE2_PENDING` shortcut is gone). Email
ingestion and digests arrive in later phases.

### DRIVE-5 — manual lesson management + usability

Two new write tools (tier `write_auto`, audit-logged, idempotent), routed via the
`log` label (the only write-allowing path): `add_lesson(date, start_time,
end_time?, instructor?, lesson_type?)` records a lesson Daria booked in the
booking app — `lesson_type` is `rijles` (default), `proefles` (trial/mock lesson),
or `exam` (the real CBR practical exam); `cancel_lesson(date | session_id)`
cancels a recorded lesson. Both are picked up
by `get_next_lessons`. Telegram replies are sent with `parse_mode=HTML`; the
answer prompt emits `<b>`/`<i>` (no markdown), residual markdown is stripped
before send. The semantic-layer `pace()` returns a `verdict` of `no_exam_date`
(with counts, `on_track=null` — never `on_track=false`) when `EXAM_DATE` is
unset, else `on_track`/`off_track`. Answers end with the information and never
offer follow-up actions or questions (the bot has no conversation memory).

### DRIVE-7 — language enforcement + first-real-usage gaps

Reply language is detected in code (Cyrillic-ratio heuristic, en/ru only) and an
explicit `REPLY IN: English|Russian` directive is injected at the top of the
answer/refusal prompt every message. A guardrail checks the answer's Cyrillic
ratio against the directive: a mismatch (e.g. an English question whose answer
drifted into Russian when the tool results were in Russian) triggers one
corrective retry, then a visibly degraded reply prefixed with ⚠️. Two
Vehicle-control skills Daria's instructor treats as distinct — braking control
(`remmen`) and acceleration (`versnellen`) — were added to the seeded CBR matrix
(Alembic migration `0003`) so free-text notes match them instead of falling
through to general notes.

### DRIVE-8 — production week-one findings

Four fixes from the first week of real usage:

- **Resilience.** Transient LLM/API errors (`LlmCallError`,
  `RouterUnavailableError`) now get one automatic retry with a short backoff
  before the user-facing "Sorry, I couldn't process that right now" fallback.
  Each retry is logged with the underlying error class (`bot.transient_retry`).
  Two week-one failures that both succeeded on an immediate rephrase are now
  recovered automatically. Writes are safe to re-run: write tools carry
  idempotency keys and dedupe against the failed attempt's audit rows.
- **Session lifecycle.** `log_lesson` attaching notes to a session dated today
  or earlier that is still `status=scheduled` now marks it `completed`, so
  `pace()` stops counting a finished lesson as "1 lesson remaining". The one
  affected production row (session 7) is flipped via Alembic migration `0004`.
- **Router.** Notes-by-date phrasings ("what are my notes from 13/08?") were
  mislabelled `other` and refused. The router prompt and `evals/golden.yaml`
  gained notes-by-date examples (English + Russian) routing to `lookup`.
- **Copy.** A production refusal said "our driving school's booking app". The
  refusal prompt now says Daria's ("your driving school's booking app") and
  explicitly forbids "our" — the copilot is not a driving school.

Rebuild the knowledge base from the PDF (requires `DEEPL_API_KEY` for the
English translation):

```bash
uv run python scripts/build_rijprocedure_nl.py   # PDF -> rijprocedure-b.nl.md
uv run python scripts/build_rijprocedure_en.py   # DeepL -> rijprocedure-b.en.md
uv run python scripts/build_cbr_topics.py        # verbatim topic excerpts
```
