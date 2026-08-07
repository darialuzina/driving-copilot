from __future__ import annotations

from app.config import get_settings


def _db_name(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def test_test_database_url_ends_with_test_suffix() -> None:
    """Regression test: the test database URL must point to a database ending with _test."""
    settings = get_settings()
    name = _db_name(settings.test_database_url)
    assert name.endswith("_test"), (
        f"TEST_DATABASE_URL must point to a database ending with '_test', got '{name}'"
    )


def test_test_database_url_differs_from_dev_database_url() -> None:
    """Regression test: the test database and the dev database must never be the same.

    If they are, pytest will truncate or overwrite the live bot's data — the exact
    bug that destroyed Daria's backfill in the shared workshop container.
    """
    settings = get_settings()
    dev = _db_name(settings.database_url)
    test = _db_name(settings.test_database_url)
    assert test != dev, (
        f"TEST_DATABASE_URL ({test}) must not equal DATABASE_URL ({dev}) — "
        "tests would destroy the live bot's data"
    )
