from __future__ import annotations

import html
import re

# Telegram sends messages with parse_mode=HTML (DRIVE-5). The answer model is told
# to use <b>/<i> for emphasis and no markdown. As a safety net:
#   - strip_markdown(): remove residual markdown punctuation the model may emit
#     despite the instruction (so it never reaches the user as literal **text**);
#   - sanitize_html_for_telegram(): escape stray & < > and keep only the small set
#     of Telegram-allowed tags, so an answer containing e.g. "speed < 50" or an
#     accidental "<marquee>" cannot break rendering or inject markup.
#   - to_telegram_html(): the composed helper used by the bot send path.

# Telegram-supported inline tags we allow (kept intentionally minimal).
_ALLOWED_TAG_RE = re.compile(
    r"(</?(?:b|i|u|s|code|pre)(?:\s[^<>]*)?/?>)",
    re.IGNORECASE,
)

_MARKDOWN_CODE = re.compile(r"`([^`\n]+?)`")
_MARKDOWN_BOLD_STAR = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_MARKDOWN_BOLD_UNDER = re.compile(r"__(.+?)__", re.DOTALL)
# *italic* — avoid matching ** (handled above) and lone asterisks used as list markers.
_MARKDOWN_ITALIC_STAR = re.compile(r"(?<!\w)\*(?!\s)([^*\n]+?)(?<!\s)\*(?!\w)")
# _italic_ — only between word boundaries so we don't mangle snake_case identifiers.
_MARKDOWN_ITALIC_UNDER = re.compile(r"(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])")
_MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MARKDOWN_LIST = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Remove common markdown punctuation the model may emit by accident.

    Telegram renders our messages as HTML, so any leftover markdown would show up as
    literal characters. This strips bold/italic/code spans, heading hashes, and list
    bullets, leaving the inner text. It does NOT touch HTML tags (kept for the
    sanitizer).
    """
    text = _MARKDOWN_CODE.sub(r"\1", text)
    text = _MARKDOWN_BOLD_STAR.sub(r"\1", text)
    text = _MARKDOWN_BOLD_UNDER.sub(r"\1", text)
    text = _MARKDOWN_ITALIC_STAR.sub(r"\1", text)
    text = _MARKDOWN_ITALIC_UNDER.sub(r"\1", text)
    text = _MARKDOWN_HEADING.sub("", text)
    text = _MARKDOWN_LIST.sub("", text)
    return text


def sanitize_html_for_telegram(text: str) -> str:
    """Escape stray & < > and keep only the allowed Telegram inline tags.

    The model is instructed to emit <b>/<i> for emphasis. Anything else that looks
    like a tag, and every bare &/</>, is HTML-escaped so it renders literally and
    cannot break Telegram's HTML parser.
    """
    out: list[str] = []
    for part in _ALLOWED_TAG_RE.split(text):
        if part and _ALLOWED_TAG_RE.fullmatch(part):
            out.append(part.lower())
        else:
            out.append(html.escape(part, quote=False))
    return "".join(out)


def to_telegram_html(text: str) -> str:
    """Strip residual markdown, then sanitize for Telegram HTML parse mode."""
    return sanitize_html_for_telegram(strip_markdown(text))
