from __future__ import annotations

import pytest

from app.services.tools import AddLessonParams, CancelLessonParams, LogLessonParams


def test_log_lesson_valid_today() -> None:
    params = LogLessonParams.model_validate(
        {"date": "today", "skills": [{"skill": "parking", "assessment": "good", "note": "ok"}]}
    )
    assert params.date == "today"
    assert params.skills[0].assessment.value == "good"


def test_log_lesson_valid_iso_date() -> None:
    params = LogLessonParams.model_validate({"date": "2026-08-06"})
    assert params.date == "2026-08-06"


def test_log_lesson_rejects_bad_date() -> None:
    with pytest.raises(ValueError):
        LogLessonParams.model_validate({"date": "August 6"})


def test_log_lesson_rejects_bad_assessment() -> None:
    with pytest.raises(ValueError):
        LogLessonParams.model_validate(
            {"skills": [{"skill": "parking", "assessment": "great", "note": "ok"}]}
        )


# --- add_lesson / cancel_lesson params (DRIVE-5) ---


def test_add_lesson_valid_minimal() -> None:
    params = AddLessonParams.model_validate({"date": "2026-08-12", "start_time": "15:00"})
    assert params.date == "2026-08-12"
    assert params.start_time == "15:00"
    assert params.end_time is None
    assert params.instructor is None


def test_add_lesson_valid_full() -> None:
    params = AddLessonParams.model_validate(
        {"date": "2026-08-12", "start_time": "15:00", "end_time": "16:00", "instructor": "Marco"}
    )
    assert params.instructor == "Marco"


def test_add_lesson_rejects_bad_date() -> None:
    with pytest.raises(ValueError):
        AddLessonParams.model_validate({"date": "Aug 12", "start_time": "15:00"})


def test_add_lesson_rejects_bad_start_time() -> None:
    with pytest.raises(ValueError):
        AddLessonParams.model_validate({"date": "2026-08-12", "start_time": "3pm"})
    with pytest.raises(ValueError):
        AddLessonParams.model_validate({"date": "2026-08-12", "start_time": "25:00"})


def test_add_lesson_rejects_bad_end_time() -> None:
    with pytest.raises(ValueError):
        AddLessonParams.model_validate(
            {"date": "2026-08-12", "start_time": "15:00", "end_time": "99:99"}
        )


def test_cancel_lesson_valid_by_date() -> None:
    params = CancelLessonParams.model_validate({"date": "2026-08-12"})
    assert params.date == "2026-08-12"
    assert params.session_id is None


def test_cancel_lesson_valid_by_session_id() -> None:
    params = CancelLessonParams.model_validate({"session_id": 7})
    assert params.session_id == 7
    assert params.date is None


def test_cancel_lesson_requires_exactly_one_of_date_or_session_id() -> None:
    with pytest.raises(ValueError):
        CancelLessonParams.model_validate({})
    with pytest.raises(ValueError):
        CancelLessonParams.model_validate({"date": "2026-08-12", "session_id": 7})


def test_cancel_lesson_rejects_bad_date() -> None:
    with pytest.raises(ValueError):
        CancelLessonParams.model_validate({"date": "Friday"})
