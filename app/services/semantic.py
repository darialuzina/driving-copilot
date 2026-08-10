from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

# Semantic layer — the only definitions of "skill_status", "pace", and "stale"
# in the system (spec section 3). The LLM never computes these; tools call these
# functions and answers repeat their output.

_STALE_DAYS = 21


class SkillStatus(StrEnum):
    """Derived status of a single skill, from its assessment history.

    Definitions (spec section 3):
    - not_started: no notes ever.
    - weak:        the most recent assessment is needs_attention.
    - solid:       the last two assessments are both good.
    - in_progress: anything else.
    """

    NOT_STARTED = "not_started"
    WEAK = "weak"
    SOLID = "solid"
    IN_PROGRESS = "in_progress"


@dataclass(frozen=True)
class PaceResult:
    """Output of pace(): lessons remaining vs skills not yet solid (spec section 3).

    `verdict` is the human-facing verdict:
    - `no_exam_date`: no exam date is set, so on_track is undefined (`on_track` is None);
      the counts are still returned so the answer can say "X lessons scheduled, Y gaps".
    - `on_track`: exam date set and lessons_left >= weak_or_missing_count.
    - `off_track`: exam date set and lessons_left < weak_or_missing_count.
    """

    lessons_left: int
    weak_or_missing_count: int
    on_track: bool | None
    verdict: str


def skill_status(assessments: list[str]) -> SkillStatus:
    """Status of a skill from its assessments in chronological order (oldest first).

    - no notes           -> not_started
    - last is needs_attention -> weak
    - last two are good   -> solid
    - otherwise          -> in_progress
    """
    if not assessments:
        return SkillStatus.NOT_STARTED
    if assessments[-1] == "needs_attention":
        return SkillStatus.WEAK
    if len(assessments) >= 2 and assessments[-1] == "good" and assessments[-2] == "good":
        return SkillStatus.SOLID
    return SkillStatus.IN_PROGRESS


def pace(
    *,
    lessons_left: int,
    solid_count: int,
    total_exam_relevant: int,
    exam_date: date | None,
) -> PaceResult:
    """Pace verdict (spec section 3, DRIVE-5).

    weak_or_missing_count = total exam-relevant skills minus the solid ones.
    With no exam date, on_track is undefined: return verdict `no_exam_date`
    (never `on_track=False`), with the counts so the answer can still report them.
    """
    weak_or_missing = max(0, total_exam_relevant - solid_count)
    if exam_date is None:
        return PaceResult(
            lessons_left=lessons_left,
            weak_or_missing_count=weak_or_missing,
            on_track=None,
            verdict="no_exam_date",
        )
    on_track = lessons_left >= weak_or_missing
    return PaceResult(
        lessons_left=lessons_left,
        weak_or_missing_count=weak_or_missing,
        on_track=on_track,
        verdict="on_track" if on_track else "off_track",
    )


def is_stale(status: SkillStatus, last_practiced: date | None, today: date) -> bool:
    """A solid skill not practiced in 21+ days is flagged for refresh (spec section 3)."""
    if status != SkillStatus.SOLID or last_practiced is None:
        return False
    return (today - last_practiced).days >= _STALE_DAYS
