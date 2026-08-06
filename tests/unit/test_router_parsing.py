from __future__ import annotations

from app.services.router import extract_label


def test_extract_label_plain() -> None:
    assert extract_label("lookup") == "lookup"
    assert extract_label("  Analytics\n") == "analytics"


def test_extract_label_json() -> None:
    assert extract_label('{"label": "log"}') == "log"
    assert extract_label('```json\n{"label": "other"}\n```') == "other"


def test_extract_label_garbage_falls_through() -> None:
    assert extract_label("sure, here is the answer") == "sure, here is the answer"
