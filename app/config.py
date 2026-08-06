from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Driving Copilot configuration. Values come from the environment or .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- database (PostgreSQL via docker-compose, per .agents/agents/database.md) ---
    database_url: str = "postgresql+psycopg://app:app@localhost:5433/app"

    # --- Telegram ---
    telegram_bot_token: str = ""
    allowed_chat_id: int | None = None  # only this chat may talk to the bot

    # --- LLM (OpenRouter, OpenAI-compatible) ---
    # Deliberately NOT named OPENROUTER_API_KEY: that name is exported globally in the
    # coding-agent shell and pydantic-settings would let the real env var override .env.
    llm_api_key: str = ""
    llm_base_url: str = "https://openrouter.ai/api/v1"
    router_model: str = "openai/gpt-4.1-mini"
    answer_model: str = "mistralai/mistral-large-2512"

    # --- domain config ---
    exam_date: str | None = None  # YYYY-MM-DD, optional until known
    timezone: str = "Europe/Amsterdam"

    # --- eval/observability ---
    router_log_path: Path = Path("logs/router.jsonl")

    # --- fixtures ---
    backfill_path: Path = Path("fixtures/backfill.yaml")


def get_settings() -> Settings:
    return Settings()
