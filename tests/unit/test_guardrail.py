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
