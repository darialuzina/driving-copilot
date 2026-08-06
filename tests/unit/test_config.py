from __future__ import annotations

import pytest

from app.config import Settings, get_settings


def test_get_settings_returns_settings_instance() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)


def test_settings_defaults_are_present() -> None:
    settings = Settings()
    assert settings.code_length == 7
    assert settings.base_url == "http://127.0.0.1:8000"
    assert settings.database_url.startswith("postgresql")


def test_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODE_LENGTH", "9")
    monkeypatch.setenv("BASE_URL", "https://sho.rt")
    settings = Settings()
    assert settings.code_length == 9
    assert settings.base_url == "https://sho.rt"
