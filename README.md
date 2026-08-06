# Driving Copilot

A Telegram-based AI copilot for Daria's driving-exam preparation. Tracks lessons
(parsed from On My Way booking emails + quick notes after each lesson), maps progress
against the official CBR exam requirements, and answers questions in chat.

Architecture: small-model router → typed tools → deterministic code → guardrails → evals.
The model chooses and phrases; code computes. Every fact in an answer comes from a tool result.

See `driving-copilot-spec_1.md` for the full specification.

## Stack

- Python 3.14, async SQLAlchemy 2.0, PostgreSQL (docker-compose), Alembic
- `python-telegram-bot` v21 (async), `openai` client against OpenRouter
- Two models via env: `ROUTER_MODEL` (classification) and `ANSWER_MODEL` (tool-calling + answers)

## Setup

```bash
uv sync
docker compose up -d db
cp .env.example .env   # then fill in TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_ID, LLM_API_KEY
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

## Phase 1 (current)

DB schema + seeded skills + backfill (spec section 11), Telegram bot with `/start`,
intent router (6 labels), and tools: `get_next_lessons`, `get_lesson_history`,
`log_lesson` (auto-approved write via chat). Analytics, gap analysis, CBR knowledge,
email ingestion, digests, and evals arrive in later phases.
