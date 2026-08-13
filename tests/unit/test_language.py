from __future__ import annotations

from app.services.agent import answer_language_ok
from app.services.prompts import detect_language

# --- detect_language (Cyrillic-ratio heuristic, en/ru only) ---


# --- detect_language (Cyrillic-ratio heuristic, en/ru only) ---


def test_detect_language_english() -> None:
    assert detect_language("when is my next lesson?") == "English"


def test_detect_language_russian() -> None:
    assert detect_language("когда у меня следующий урок?") == "Russian"


def test_detect_language_dutch_term_embedded_in_english_is_english() -> None:
    # Dutch driving vocabulary embedded in an English sentence is still English.
    assert detect_language("how did my rotondes go?") == "English"


def test_detect_language_dutch_term_embedded_in_russian_is_russian() -> None:
    # Dutch vocabulary embedded in a Russian sentence stays Russian.
    assert detect_language("сегодня делали bijzondere verrichtingen, нормально") == "Russian"


def test_detect_language_empty_or_digits_defaults_to_english() -> None:
    assert detect_language("") == "English"
    assert detect_language("2026-08-13 15:00") == "English"


def test_detect_language_short_russian_word_is_russian() -> None:
    assert detect_language("привет!") == "Russian"


# --- answer_language_ok guardrail (Cyrillic-ratio match to directive) ---


def test_language_ok_english_answer_for_english_directive() -> None:
    assert (
        answer_language_ok(
            "Your weak areas are roundabouts and speed adaptation.", "English"
        )
        is True
    )


def test_language_ok_russian_answer_drifts_from_english_directive() -> None:
    # The bug: an English question whose answer drifted into Russian.
    drifted = "Ваши слабые места — rotondes и speed adaptation."
    assert answer_language_ok(drifted, "English") is False


def test_language_ok_russian_answer_for_russian_directive() -> None:
    assert answer_language_ok("Ваши слабые места — rotondes и speed adaptation.", "Russian") is True


def test_language_ok_english_answer_drifts_from_russian_directive() -> None:
    assert answer_language_ok("Your weak areas are roundabouts.", "Russian") is False


def test_language_ok_english_answer_with_kb_citation_is_english() -> None:
    # A docs answer in English carries an English provenance marker; no Cyrillic.
    assert (
        answer_language_ok(
            "Rijprocedure B, §3.7: the examiner picks about two manoeuvres.", "English"
        )
        is True
    )


def test_language_ok_russian_answer_with_english_citation_stays_russian() -> None:
    # A Russian docs answer may embed an English KB citation but stays mostly Cyrillic.
    answer = (
        "Rijprocedure B, §3.7: экзаменатор выбирает около двух "
        "bijzondere verrichtingen, например fileparkeren и hellingproef."
    )
    assert answer_language_ok(answer, "Russian") is True


def test_language_ok_no_directive_passes() -> None:
    assert answer_language_ok("Что угодно на русском.", "") is True
    assert answer_language_ok("Anything in English.", "") is True


def test_language_ok_empty_answer_passes() -> None:
    assert answer_language_ok("", "English") is True
    assert answer_language_ok("", "Russian") is True
