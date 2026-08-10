"""Regression test for the backup/restore round-trip (RUNBOOK section 8).

Exercises the documented restore procedure: dumps the test database with
``pg_dump`` (run inside the ``db`` container, matching the production backup
sidecar), restores the dump into a scratch database created on the same
Postgres instance, and asserts the row counts match. This is the test
behind the RUNBOOK's "Test the restore (against a scratch database)" steps.

It needs the docker-compose ``db`` container running (the same one the rest
of the integration suite uses), because it shells out to ``pg_dump``/``psql``
inside that container. The test is skipped when docker is unavailable.
"""

from __future__ import annotations

import subprocess
from collections.abc import Generator

import pytest
from sqlalchemy.engine import make_url

from app.config import get_settings

_source_db = make_url(get_settings().test_database_url).database
assert _source_db is not None, "test_database_url must include a database name"
SOURCE_DB: str = _source_db
SCRATCH_DB = "driving_copilot_restore_test"

# Tables whose row counts must survive the dump/restore round-trip.
TABLES = ("sessions", "skills", "lesson_notes", "audit_log")


def _docker_available() -> bool:
    try:
        subprocess.run(
            ["docker", "compose", "ps", "-q", "db"],
            capture_output=True,
            check=True,
            text=True,
            timeout=20,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return False
    return True


pytestmark = pytest.mark.skipif(not _docker_available(), reason="docker compose db not running")


def _exec_db(args: list[str], stdin: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    """Run a command inside the ``db`` container; return stdout bytes."""
    return subprocess.run(
        ["docker", "compose", "exec", "-T", "db", *args],
        input=stdin,
        capture_output=True,
        check=True,
        timeout=60,
    )


def _psql(database: str, sql: str) -> str:
    """Run a SQL statement in ``database`` via psql; return stdout text."""
    res = _exec_db(["psql", "-U", "app", "-d", database, "-t", "-A", "-c", sql])
    return res.stdout.decode().strip()


def _count(database: str, table: str) -> int:
    return int(_psql(database, f"SELECT count(*) FROM {table};"))


def _pg_dump(database: str) -> bytes:
    return _exec_db(
        [
            "pg_dump",
            "-U",
            "app",
            "--no-owner",
            "--no-privileges",
            "--dbname",
            database,
        ]
    ).stdout


@pytest.fixture
def scratch_db() -> Generator[None]:
    """Create a fresh scratch database for the test; drop it on teardown."""
    _psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB};")
    _psql("postgres", f"CREATE DATABASE {SCRATCH_DB};")
    yield
    # Close any lingering connections before dropping.
    _psql(
        "postgres",
        f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
        f"WHERE datname = '{SCRATCH_DB}' AND pid <> pg_backend_pid();",
    )
    _psql("postgres", f"DROP DATABASE IF EXISTS {SCRATCH_DB};")


async def test_backup_restore_round_trip_preserves_row_counts(scratch_db: None) -> None:
    """A pg_dump of the test db, restored into a scratch db, keeps all row counts."""
    dump = _pg_dump(SOURCE_DB)
    assert dump, "pg_dump produced an empty dump"

    # Load the dump into the scratch database (psql reads SQL from stdin).
    _exec_db(["psql", "-U", "app", "-d", SCRATCH_DB, "-v", "ON_ERROR_STOP=1"], stdin=dump)

    for table in TABLES:
        source_count = _count(SOURCE_DB, table)
        scratch_count = _count(SCRATCH_DB, table)
        assert scratch_count == source_count, (
            f"{table}: scratch has {scratch_count} rows, source has {source_count}"
        )
