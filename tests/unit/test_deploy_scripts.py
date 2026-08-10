"""Unit tests for the deploy/backup scripts (no docker, no network).

These cover the parts of the operator scripts that are pure logic:

- ``docker/backup.sh`` retention (keep the newest 7 ``.sql.gz`` files).
- ``scripts/check_env.sh`` .env key validation (names only, never values).

The full backup/restore round-trip is covered by
``tests/integration/test_backup_restore.py``.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

# The exact retention snippet used in docker/backup.sh (KEEP=7, keep newest).
PRUNE_SNIPPET = r"""
KEEP=7
ls -1t "$1"/driving_copilot-*.sql.gz 2>/dev/null | tail -n +$((KEEP + 1)) | \
    while IFS= read -r old; do [ -n "$old" ] && rm -f "$old"; done
"""


def _make_backups(dir_path: Path, n: int) -> list[Path]:
    files: list[Path] = []
    for i in range(n):
        f = dir_path / f"driving_copilot-2026010{i}-030000.sql.gz"
        f.write_bytes(b"")
        # Force increasing mtime so `ls -t` ordering is deterministic across
        # filesystems whose timestamp granularity may be coarse.
        ts = 1_700_000_000 + i
        os.utime(f, (ts, ts))
        files.append(f)
    return files


def test_backup_retention_keeps_newest_7(tmp_path: Path) -> None:
    files = _make_backups(tmp_path, 10)
    subprocess.run(["sh", "-c", PRUNE_SNIPPET, "--", str(tmp_path)], check=True)

    remaining = sorted(tmp_path.glob("driving_copilot-*.sql.gz"))
    assert len(remaining) == 7
    # The 7 newest (highest mtime) survive; the 3 oldest are pruned.
    expected = {f.name for f in files[-7:]}
    assert {f.name for f in remaining} == expected


def test_backup_retention_keeps_all_when_under_limit(tmp_path: Path) -> None:
    _make_backups(tmp_path, 3)
    subprocess.run(["sh", "-c", PRUNE_SNIPPET, "--", str(tmp_path)], check=True)
    remaining = sorted(tmp_path.glob("driving_copilot-*.sql.gz"))
    assert len(remaining) == 3


def _run_check_env(env_path: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", str(REPO / "scripts" / "check_env.sh"), str(env_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_env_passes_when_all_keys_present(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc123\n"
        "ALLOWED_CHAT_ID=12345\n"
        "LLM_API_KEY=sk-or-...\n"
        "# a comment, ignored\n"
        "TIMEZONE=Europe/Amsterdam\n"
    )
    res = _run_check_env(env)
    assert res.returncode == 0
    assert "TELEGRAM_BOT_TOKEN present" in res.stdout
    assert "ALLOWED_CHAT_ID present" in res.stdout
    assert "LLM_API_KEY present" in res.stdout
    # Values must never be printed.
    assert "abc123" not in res.stdout
    assert "12345" not in res.stdout


def test_check_env_fails_when_a_key_is_missing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("TELEGRAM_BOT_TOKEN=abc123\nALLOWED_CHAT_ID=12345\n")  # no LLM_API_KEY
    res = _run_check_env(env)
    assert res.returncode != 0
    assert "LLM_API_KEY MISSING or empty" in res.stderr


def test_check_env_fails_when_a_key_is_empty(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text(
        "TELEGRAM_BOT_TOKEN=abc123\n"
        "ALLOWED_CHAT_ID=12345\n"
        "LLM_API_KEY=\n"  # present but empty
    )
    res = _run_check_env(env)
    assert res.returncode != 0
    assert "LLM_API_KEY MISSING or empty" in res.stderr


def test_check_env_fails_when_env_file_missing(tmp_path: Path) -> None:
    res = _run_check_env(tmp_path / "nope.env")
    assert res.returncode != 0
    assert "not found" in res.stderr
