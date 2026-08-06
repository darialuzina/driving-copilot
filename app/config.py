from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Конфигурация приложения. Значения берутся из окружения или .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/app"
    base_url: str = "http://127.0.0.1:8000"
    code_length: int = 7


def get_settings() -> Settings:
    return Settings()
