from __future__ import annotations

import re

from app.bot import START_TEXT
from app.services.prompts import (
    ANSWER_SYSTEM_PROMPT,
    REFUSAL_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
)

LABELS = ("lookup", "analytics", "log", "docs", "smalltalk", "other")

_CYRILLIC = re.compile(r"[А-Яа-яЁё]")
# Dutch driving terms that may appear as embedded vocabulary (not full Dutch sentences).
_DUTCH_TERMS = ("rotondes", "bijzondere verrichtingen", "spiegels")


def _example_lines() -> list[str]:
    lines: list[str] = []
    in_examples = False
    for line in ROUTER_SYSTEM_PROMPT.splitlines():
        if line.strip().startswith("Examples:"):
            in_examples = True
            continue
        if in_examples and "->" in line:
            lines.append(line.strip().strip("- ").strip('"'))
    return lines


def test_router_prompt_has_two_examples_per_label() -> None:
    lines = _example_lines()
    for label in LABELS:
        matching = [ln for ln in lines if ln.endswith(f"-> {label}")]
        assert len(matching) >= 2, f"label {label!r} has only {len(matching)} examples"


def test_router_prompt_each_label_has_russian_and_english_example() -> None:
    lines = _example_lines()
    for label in LABELS:
        matching = [ln for ln in lines if ln.endswith(f"-> {label}")]
        has_ru = any(_CYRILLIC.search(ln) for ln in matching)
        has_en = any(not _CYRILLIC.search(ln) for ln in matching)
        assert has_ru, f"label {label!r} has no Russian example"
        assert has_en, f"label {label!r} has no English example"


def test_router_prompt_has_dutch_embedded_mixed_examples() -> None:
    lines = _example_lines()
    # At least two examples embed Dutch driving terms inside a ru/en sentence.
    dutch = [ln for ln in lines if any(term in ln.lower() for term in _DUTCH_TERMS)]
    assert len(dutch) >= 2, "expected >=2 Dutch-term-embedded examples"
    # The Dutch-term examples must themselves be Russian or English sentences (contain
    # Cyrillic or plain Latin), not full Dutch sentences.
    assert any(_CYRILLIC.search(ln) for ln in dutch), "one Dutch-term example should be Russian"


def test_router_prompt_no_full_dutch_sentences_in_examples() -> None:
    # No example line is a full Dutch sentence: every example contains Cyrillic or is
    # English (Latin + common words). Heuristic: reject lines that look fully Dutch
    # (start with a Dutch question word and contain only Dutch vocabulary).
    dutch_starts = ("wat ", "hoe ", "welke ", "waar ", "kun je ", "kan ik ")
    for ln in _example_lines():
        low = ln.lower()
        assert not low.startswith(dutch_starts), f"full-Dutch example not allowed: {ln!r}"


def test_answer_prompt_rule_one_is_language() -> None:
    assert "Reply in the language of the user's message" in ANSWER_SYSTEM_PROMPT


def test_refusal_prompt_lists_current_capabilities_no_phases() -> None:
    assert "Phase" not in REFUSAL_SYSTEM_PROMPT
    assert "lessons" in REFUSAL_SYSTEM_PROMPT


def test_start_text_lists_capabilities_no_phase_numbers() -> None:
    assert "Phase" not in START_TEXT
    assert "look up" in START_TEXT.lower()
    assert "log what you practiced" in START_TEXT.lower()
