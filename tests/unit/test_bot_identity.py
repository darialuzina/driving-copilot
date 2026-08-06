from __future__ import annotations

from app.bot import is_allowed_chat
from app.config import Settings


def test_allowed_matching_chat() -> None:
    assert is_allowed_chat(123, Settings(allowed_chat_id=123)) is True


def test_blocked_foreign_chat() -> None:
    assert is_allowed_chat(999, Settings(allowed_chat_id=123)) is False


def test_no_chat_object() -> None:
    assert is_allowed_chat(None, Settings(allowed_chat_id=123)) is False


def test_allowed_chat_id_unset_blocks_all() -> None:
    assert is_allowed_chat(123, Settings(allowed_chat_id=None)) is False
