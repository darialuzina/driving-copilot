from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.logging import configure_logging
from app.services.backfill import load_backfill
from app.services.router import OpenRouterLlmClient

# Configure structlog before importing app.bot, so the service modules' module-level
# loggers are bound to the configured renderer (cache_logger_on_first_use=True).
configure_logging()

from app.bot import Copilot, run  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Driving Copilot")
    parser.add_argument("command", nargs="?", default="bot", choices=["bot", "backfill"])
    args = parser.parse_args(argv)

    settings = get_settings()
    if args.command == "backfill":
        asyncio.run(_run_backfill(settings))
        return 0

    if not settings.telegram_bot_token:
        print("TELEGRAM_BOT_TOKEN is not set", file=sys.stderr)
        return 1
    client = OpenRouterLlmClient(settings.llm_api_key, settings.llm_base_url)
    copilot = Copilot.build(client, settings)
    run(copilot, settings)
    return 0


async def _run_backfill(settings: Settings) -> None:
    async with get_sessionmaker()() as session:
        await load_backfill(session, settings.backfill_path)


if __name__ == "__main__":
    raise SystemExit(main())
