from __future__ import annotations

import re
from difflib import SequenceMatcher

from app.db.models import SkillModel

_NORMALIZE_RE = re.compile(r"[^a-z0-9 ]+")


def _normalize(text: str) -> str:
    return _NORMALIZE_RE.sub(" ", text.lower()).strip()


def fuzzy_match_skill(query: str, skills: list[SkillModel]) -> SkillModel | None:
    """Match a free-text skill name against the seeded skills table.

    Order of preference (deterministic):
      1. exact match on the English name
      2. exact match on the Dutch name_nl
      3. substring match (query inside skill name or vice-versa)
      4. token overlap (English or Dutch)
      5. difflib ratio above a threshold
    When multiple candidates tie on a step, the one with the shorter name wins
    (the more general term, e.g. "parallel parking" over "bay parking forward/reverse").
    """
    if not query.strip():
        return None
    q = _normalize(query)

    def by_shortest(candidates: list[SkillModel]) -> SkillModel | None:
        if not candidates:
            return None
        return min(candidates, key=lambda s: len(s.name))

    # 1. exact English name
    for skill in skills:
        if _normalize(skill.name) == q:
            return skill

    # 2. exact Dutch name
    for skill in skills:
        if skill.name_nl and _normalize(skill.name_nl) == q:
            return skill

    # 3. substring either direction
    substring = [
        skill
        for skill in skills
        if q and (_normalize(skill.name) in q or q in _normalize(skill.name))
    ]
    chosen = by_shortest(substring)
    if chosen is not None:
        return chosen

    # 4. token overlap (>= 1 shared significant token)
    q_tokens = {tok for tok in q.split() if len(tok) > 2}
    if q_tokens:
        overlap: list[SkillModel] = []
        for skill in skills:
            skill_tokens = {tok for tok in _normalize(skill.name).split() if len(tok) > 2} | {
                tok for tok in _normalize(skill.name_nl or "").split() if len(tok) > 2
            }
            if q_tokens & skill_tokens:
                overlap.append(skill)
        chosen = by_shortest(overlap)
        if chosen is not None:
            return chosen

    # 5. difflib ratio
    best: SkillModel | None = None
    best_score = 0.0
    for skill in skills:
        score = max(
            SequenceMatcher(None, q, _normalize(skill.name)).ratio(),
            SequenceMatcher(None, q, _normalize(skill.name_nl or "")).ratio(),
        )
        if score > best_score:
            best_score = score
            best = skill
    if best is not None and best_score >= 0.6:
        return best

    return None
