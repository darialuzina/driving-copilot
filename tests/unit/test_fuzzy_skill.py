from __future__ import annotations

from app.db.models import SkillModel
from app.services.skills import fuzzy_match_skill


def _skill(name: str, name_nl: str | None = None, category: str = "c") -> SkillModel:
    s = SkillModel(category=category, name=name, name_nl=name_nl)
    s.id = hash(name) % 1000  # type: ignore[assignment]
    return s


SKILLS = [
    _skill("parallel parking", "fileparkeren", "Special maneuvers"),
    _skill("bay parking forward/reverse", "parkeervak", "Special maneuvers"),
    _skill("speed adaptation", "snelheid aanpassen", "Highway"),
    _skill("roundabouts", "rotondes", "Intersections"),
    _skill("mirror routine", "spiegels", "Observation"),
]


def test_exact_name() -> None:
    matched = fuzzy_match_skill("roundabouts", SKILLS)
    assert matched is not None
    assert matched.name == "roundabouts"


def test_exact_dutch() -> None:
    matched = fuzzy_match_skill("rotondes", SKILLS)
    assert matched is not None
    assert matched.name == "roundabouts"


def test_substring_picks_shortest_general() -> None:
    # "parking" matches both parking skills by substring; the shorter (more general) wins.
    matched = fuzzy_match_skill("parking", SKILLS)
    assert matched is not None
    assert matched.name == "parallel parking"


def test_token_overlap() -> None:
    matched = fuzzy_match_skill("speed work", SKILLS)
    assert matched is not None
    assert matched.name == "speed adaptation"


def test_unmatched_returns_none() -> None:
    assert fuzzy_match_skill("quantum physics", SKILLS) is None


def test_empty_query() -> None:
    assert fuzzy_match_skill("", SKILLS) is None
