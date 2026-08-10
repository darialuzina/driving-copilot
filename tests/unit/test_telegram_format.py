from __future__ import annotations

import pytest

from app.services.telegram_format import (
    sanitize_html_for_telegram,
    strip_markdown,
    to_telegram_html,
)

# --- strip_markdown ---


def test_strip_markdown_removes_bold_asterisks() -> None:
    assert strip_markdown("**bold**") == "bold"


def test_strip_markdown_removes_italic_asterisks() -> None:
    assert strip_markdown("*italic*") == "italic"


def test_strip_markdown_removes_bold_underscores() -> None:
    assert strip_markdown("__bold__") == "bold"


def test_strip_markdown_removes_italic_underscores() -> None:
    assert strip_markdown("an _italic_ word") == "an italic word"


def test_strip_markdown_removes_code_backticks() -> None:
    assert strip_markdown("see `code` here") == "see code here"


def test_strip_markdown_removes_heading_hashes() -> None:
    assert strip_markdown("# Heading\nbody") == "Heading\nbody"


def test_strip_markdown_removes_list_markers() -> None:
    assert strip_markdown("- one\n- two") == "one\ntwo"


def test_strip_markdown_preserves_plain_text() -> None:
    assert strip_markdown("no formatting here") == "no formatting here"


def test_strip_markdown_does_not_touch_html_tags() -> None:
    assert strip_markdown("<b>bold</b> here") == "<b>bold</b> here"


def test_strip_markdown_does_not_mangle_snake_case() -> None:
    assert strip_markdown("weak_or_missing_count is 5") == "weak_or_missing_count is 5"


# --- sanitize_html_for_telegram ---


def test_sanitize_keeps_allowed_bold_italic_tags() -> None:
    assert sanitize_html_for_telegram("<b>hi</b> <i>there</i>") == "<b>hi</b> <i>there</i>"


def test_sanitize_keeps_allowed_tags_case_insensitive_lowercased() -> None:
    assert sanitize_html_for_telegram("<B>hi</B>") == "<b>hi</b>"


def test_sanitize_escapes_unsafe_angle_bracket() -> None:
    assert sanitize_html_for_telegram("speed < 50") == "speed &lt; 50"


def test_sanitize_escapes_ampersand() -> None:
    assert sanitize_html_for_telegram("a & b") == "a &amp; b"


def test_sanitize_escapes_unknown_tag() -> None:
    assert (
        sanitize_html_for_telegram("<marquee>nope</marquee>")
        == "&lt;marquee&gt;nope&lt;/marquee&gt;"
    )


def test_sanitize_keeps_allowed_tag_around_escaped_text() -> None:
    # A raw '<' inside an allowed tag is escaped; the tag itself is preserved.
    out = sanitize_html_for_telegram("<b>speed < 50</b>")
    assert out == "<b>speed &lt; 50</b>"


# --- to_telegram_html (composed helper) ---


def test_to_telegram_html_bold_answer_no_literal_asterisks() -> None:
    # The model is told to emit <b>/<i>; a correct bold answer must render bold and
    # contain no literal asterisks.
    answer = "<b>Next lesson</b>: 2026-08-12 at 15:00 with Marco."
    out = to_telegram_html(answer)
    assert out == answer
    assert "*" not in out
    assert "<b>" in out and "</b>" in out


def test_to_telegram_html_strips_residual_markdown_then_keeps_html() -> None:
    # If the model emits markdown by accident, it is stripped; intended HTML stays.
    out = to_telegram_html("**bold** and <i>italic</i> with *more*")
    assert "*" not in out
    assert "<i>italic</i>" in out
    assert "bold" in out and "more" in out


@pytest.mark.parametrize(
    "text",
    ["plain answer", "2026-08-12 at 15:00", "no exam date set", "<b>x</b>"],
)
def test_to_telegram_html_never_returns_unescaped_unsafe_chars(text: str) -> None:
    out = to_telegram_html(text)
    # No raw < or & that aren't part of an allowed tag.
    assert "<" not in out.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace(
        "</i>", ""
    ).replace("<u>", "").replace("</u>", "").replace("<s>", "").replace("</s>", "").replace(
        "<code>", ""
    ).replace("</code>", "").replace("<pre>", "").replace("</pre>", "")
