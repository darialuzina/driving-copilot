from __future__ import annotations

from pathlib import Path
from typing import cast

import yaml

from app.services.router import VALID_LABELS

GOLDEN = Path(__file__).resolve().parents[2] / "evals" / "golden.yaml"


def _load() -> dict[str, object]:
    with GOLDEN.open(encoding="utf-8") as fh:
        data = cast(dict[str, object], yaml.safe_load(fh))
    return data


def _router_cases() -> list[dict[str, str]]:
    data = _load()
    return cast(list[dict[str, str]], data["router"])


def test_golden_yaml_exists_and_has_sections() -> None:
    data = _load()
    assert data.get("version") == 1
    assert isinstance(data.get("router"), list)
    assert isinstance(data.get("end_to_end"), list)


def test_golden_router_cases_cover_every_label() -> None:
    labels = {c["expect"] for c in _router_cases()}
    assert labels == set(VALID_LABELS)


def test_golden_router_has_mixed_language_cases() -> None:
    messages = [c["message"] for c in _router_cases()]
    # At least one Cyrillic (Russian) case and one with an embedded Dutch term.
    assert any(any("\u0430" <= ch <= "\u044f" for ch in m) for m in messages)
    assert any("rotondes" in m or "bijzondere verrichtingen" in m for m in messages)


def test_golden_end_to_end_has_assertions() -> None:
    data = _load()
    cases = cast(list[dict[str, object]], data["end_to_end"])
    for case in cases:
        assert "message" in case
        assert "must_contain" in case or "must_not_contain" in case
