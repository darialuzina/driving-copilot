from __future__ import annotations

import pytest

from app.services.tools import LogLessonParams


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
