from __future__ import annotations

from app.services.agent import containment_ok


def test_no_tool_results_passes() -> None:
    assert containment_ok("anything 5 2026-07-30", []) is True


def test_date_present_passes() -> None:
    assert containment_ok("next lesson 2026-07-30", ['{"date":"2026-07-30"}']) is True


def test_invented_date_fails() -> None:
    assert containment_ok("next lesson 2026-12-31", ['{"date":"2026-07-30"}']) is False


def test_count_present_passes() -> None:
    assert containment_ok("you have 3 lessons", ['{"count":3}']) is True


def test_invented_count_fails() -> None:
    assert containment_ok("you have 9 lessons", ['{"count":3}']) is False


def test_date_number_not_counted_twice() -> None:
    assert containment_ok("lesson on 2026-07-30", ['{"date":"2026-07-30"}']) is True


def test_real_note_id_passes() -> None:
    tool_json = ['{"tool":"log_lesson","note_ids":[1,2],"count":2}']
    assert containment_ok("logged as note 1 and note 2", tool_json) is True


def test_invented_note_id_fails_even_if_substring_present() -> None:
    # "note 3" — the number 3 appears in the blob as a count, but is not a real id.
    tool_json = ['{"tool":"log_lesson","note_ids":[1,2],"count":3}']
    assert containment_ok("logged as note 3", tool_json) is False


def test_invented_note_id_fails_when_absent() -> None:
    tool_json = ['{"tool":"log_lesson","note_ids":[1,2]}']
    assert containment_ok("logged as note 99", tool_json) is False


def test_nested_session_id_checked() -> None:
    tool_json = [
        '{"tool":"get_lesson_history","sessions":[{"id":7,"notes":[{"id":11}]}]}'
    ]
    assert containment_ok("session 7 note 11", tool_json) is True
    assert containment_ok("session 8 note 11", tool_json) is False


def test_non_id_number_still_uses_substring_check() -> None:
    # "3 lessons" is not an id reference (number before the keyword); count check applies.
    assert containment_ok("you have 3 lessons", ['{"count":3}']) is True
    assert containment_ok("you have 4 lessons", ['{"count":3}']) is False
