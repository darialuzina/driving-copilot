from __future__ import annotations

import html
from typing import Any

from app.bot import send_reply


class _FakeChat:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, text: str, parse_mode: str | None = None) -> None:
        self.calls.append({"text": text, "parse_mode": parse_mode})


def _rendered(call: dict[str, Any]) -> str:
    """What Telegram would display: the sent text decoded as parse_mode=HTML."""
    assert call["parse_mode"] == "HTML"
    return html.unescape(call["text"])


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


# --- DRIVE-9: an answer containing "&" must render as "&", never "&amp;" ---


async def test_send_reply_ampersand_renders_as_ampersand() -> None:
    # A raw ampersand in the answer escapes once to "&amp;" and, with
    # parse_mode=HTML, decodes back to "&" — no literal entity reaches Daria.
    chat = _FakeChat()
    await send_reply(chat, "tom & jerry")
    assert _rendered(chat.calls[0]) == "tom & jerry"
    assert "&amp;" not in _rendered(chat.calls[0])


async def test_send_reply_pre_escaped_ampersand_renders_as_ampersand() -> None:
    # The answer model, told to emit HTML, may itself write "&amp;". That must NOT
    # be double-escaped to "&amp;amp;" (which renders as a literal "&amp;"). Both
    # a raw "&" and a model-emitted "&amp;" render identically as "&".
    chat = _FakeChat()
    await send_reply(chat, "tom &amp; jerry")
    assert _rendered(chat.calls[0]) == "tom & jerry"
    assert "&amp;" not in _rendered(chat.calls[0])
    assert "amp;amp" not in chat.calls[0]["text"]
