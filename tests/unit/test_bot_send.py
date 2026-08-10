from __future__ import annotations

from typing import Any

from app.bot import send_reply


class _FakeChat:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, text: str, parse_mode: str | None = None) -> None:
        self.calls.append({"text": text, "parse_mode": parse_mode})


async def test_send_reply_uses_html_parse_mode() -> None:
    chat = _FakeChat()
    await send_reply(chat, "**bold** and <b>kept</b>")
    assert chat.calls[0]["parse_mode"] == "HTML"
    assert "*" not in chat.calls[0]["text"]
    assert "<b>kept</b>" in chat.calls[0]["text"]


async def test_send_reply_escapes_unsafe_markup() -> None:
    chat = _FakeChat()
    await send_reply(chat, "speed < 50 & more")
    assert chat.calls[0]["parse_mode"] == "HTML"
    assert chat.calls[0]["text"] == "speed &lt; 50 &amp; more"
