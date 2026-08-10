from __future__ import annotations

from datetime import date, timedelta

from app.services.semantic import (
    PaceResult,
    SkillStatus,
    is_stale,
    pace,
    skill_status,
)

# --- skill_status (spec section 3) ---


def test_skill_status_no_notes_is_not_started() -> None:
    assert skill_status([]) is SkillStatus.NOT_STARTED


def test_skill_status_latest_needs_attention_is_weak() -> None:
    assert skill_status(["good", "needs_attention"]) is SkillStatus.WEAK
    assert skill_status(["needs_attention"]) is SkillStatus.WEAK
    assert skill_status(["ok", "ok", "needs_attention"]) is SkillStatus.WEAK


def test_skill_status_last_two_good_is_solid() -> None:
    assert skill_status(["good", "good"]) is SkillStatus.SOLID
    assert skill_status(["needs_attention", "good", "good"]) is SkillStatus.SOLID


def test_skill_status_single_good_is_in_progress_not_solid() -> None:
    # "last two are good" requires two; a single good is in_progress.
    assert skill_status(["good"]) is SkillStatus.IN_PROGRESS


def test_skill_status_otherwise_in_progress() -> None:
    assert skill_status(["ok"]) is SkillStatus.IN_PROGRESS
    assert skill_status(["good", "ok"]) is SkillStatus.IN_PROGRESS
    assert skill_status(["ok", "needs_attention", "ok"]) is SkillStatus.IN_PROGRESS


def test_skill_status_chronological_order_matters() -> None:
    # most recent is last; latest needs_attention -> weak even if earlier were good.
    assert skill_status(["good", "good", "needs_attention"]) is SkillStatus.WEAK
    # earlier weak then two good -> solid.
    assert skill_status(["needs_attention", "good", "good"]) is SkillStatus.SOLID


# --- pace (spec section 3) ---


def test_pace_on_track_when_lessons_meet_or_exceed_gaps() -> None:
    result = pace(lessons_left=5, solid_count=3, total_exam_relevant=8)
    assert result == PaceResult(
        lessons_left=5, weak_or_missing_count=5, on_track=True
    )


def test_pace_off_track_when_not_enough_lessons() -> None:
    result = pace(lessons_left=2, solid_count=3, total_exam_relevant=8)
    assert result.weak_or_missing_count == 5
    assert result.on_track is False


def test_pace_all_solid_is_on_track() -> None:
    result = pace(lessons_left=0, solid_count=8, total_exam_relevant=8)
    assert result.weak_or_missing_count == 0
    assert result.on_track is True


def test_pace_solid_count_never_negative() -> None:
    result = pace(lessons_left=3, solid_count=10, total_exam_relevant=8)
    assert result.weak_or_missing_count == 0


# --- is_stale (spec section 3) ---


def test_stale_solid_and_not_practiced_21_days() -> None:
    today = date(2026, 8, 10)
    last = today - timedelta(days=21)
    assert is_stale(SkillStatus.SOLID, last, today) is True


def test_stale_solid_within_21_days_not_stale() -> None:
    today = date(2026, 8, 10)
    last = today - timedelta(days=20)
    assert is_stale(SkillStatus.SOLID, last, today) is False


def test_stale_not_solid_never_stale() -> None:
    today = date(2026, 8, 10)
    assert is_stale(SkillStatus.WEAK, today - timedelta(days=40), today) is False
    assert is_stale(SkillStatus.IN_PROGRESS, today - timedelta(days=40), today) is False
    assert is_stale(SkillStatus.NOT_STARTED, None, today) is False


def test_stale_solid_no_last_practiced_not_stale() -> None:
    assert is_stale(SkillStatus.SOLID, None, date(2026, 8, 10)) is False
