from __future__ import annotations

import re
from datetime import date

from app.bot import START_TEXT
from app.services.prompts import (
    ANSWER_SYSTEM_PROMPT,
    REFUSAL_SYSTEM_PROMPT,
    ROUTER_SYSTEM_PROMPT,
    answer_system_prompt,
    refusal_system_prompt,
    router_system_prompt,
    today_line,
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


# --- DRIVE-5b: today+weekday injection (per message) ---


def test_today_line_includes_weekday_and_iso_date() -> None:
    # 2026-08-10 is a Monday.
    line = today_line(date(2026, 8, 10))
    assert line == "Today is Monday 2026-08-10."


def test_router_system_prompt_prepends_today_line() -> None:
    prompt = router_system_prompt(date(2026, 8, 10))
    assert prompt.startswith("Today is Monday 2026-08-10.\n")
    # The router prompt body is preserved verbatim below the today line.
    assert ROUTER_SYSTEM_PROMPT in prompt


def test_answer_system_prompt_keeps_must_follow_in_position_one() -> None:
    prompt = answer_system_prompt(date(2026, 8, 10))
    # The #1 MUST FOLLOW rule must remain the first line (ai.md: only reliable slot).
    first_line = prompt.splitlines()[0]
    assert first_line.startswith("#1 MUST FOLLOW")
    # The today line is injected right after the #1 rule.
    assert "Today is Monday 2026-08-10." in prompt


def test_refusal_system_prompt_keeps_must_follow_in_position_one() -> None:
    prompt = refusal_system_prompt(date(2026, 8, 10))
    first_line = prompt.splitlines()[0]
    assert first_line.startswith("#1 MUST FOLLOW")
    assert "Today is Monday 2026-08-10." in prompt


def test_prompts_no_on_my_way_app_references() -> None:
    assert "On My Way" not in ANSWER_SYSTEM_PROMPT
    assert "On My Way" not in REFUSAL_SYSTEM_PROMPT
    assert "driving school's booking app" in ANSWER_SYSTEM_PROMPT
    assert "driving school's booking app" in REFUSAL_SYSTEM_PROMPT


def test_answer_prompt_clarification_rule_present() -> None:
    # The bot has no memory: missing info must trigger a "resend the full request"
    # instruction with an example, never a bare clarifying question.
    assert "RESEND THE FULL REQUEST" in ANSWER_SYSTEM_PROMPT
    assert "Пришлите одним сообщением" in ANSWER_SYSTEM_PROMPT


# --- DRIVE-7: per-message REPLY IN directive injection ---


def test_answer_prompt_injects_reply_in_directive_after_rule_one() -> None:
    prompt = answer_system_prompt(date(2026, 8, 13), reply_in="English")
    lines = prompt.splitlines()
    # The #1 MUST FOLLOW rule stays in position #1.
    assert lines[0].startswith("#1 MUST FOLLOW")
    # The REPLY IN directive is injected right after it, before the today line.
    assert lines[1] == "REPLY IN: English."
    assert lines[2] == "Today is Thursday 2026-08-13."


def test_answer_prompt_without_reply_in_only_has_today_line() -> None:
    prompt = answer_system_prompt(date(2026, 8, 13))
    lines = prompt.splitlines()
    assert lines[0].startswith("#1 MUST FOLLOW")
    assert lines[1] == "Today is Thursday 2026-08-13."


def test_refusal_prompt_injects_reply_in_directive_after_rule_one() -> None:
    prompt = refusal_system_prompt(date(2026, 8, 13), reply_in="Russian")
    lines = prompt.splitlines()
    assert lines[0].startswith("#1 MUST FOLLOW")
    assert lines[1] == "REPLY IN: Russian."
    assert lines[2] == "Today is Thursday 2026-08-13."


def test_answer_prompt_lesson_type_in_rule_four() -> None:
    # add_lesson now accepts an optional lesson_type; the prompt must mention
    # the trial-lesson -> proefles and exam synonyms.
    assert "lesson_type" in ANSWER_SYSTEM_PROMPT
    assert "proefles" in ANSWER_SYSTEM_PROMPT
    assert "trial lesson" in ANSWER_SYSTEM_PROMPT.lower()
    assert "exam" in ANSWER_SYSTEM_PROMPT.lower()
