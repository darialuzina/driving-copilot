from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path

import structlog
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.lesson_note_repository import LessonNoteRepository
from app.repositories.session_repository import SessionRepository
from app.repositories.skill_repository import SkillRepository
from app.services.skills import fuzzy_match_skill

log = structlog.get_logger()


async def load_backfill(session: AsyncSession, backfill_path: Path) -> dict[str, int]:
    """Idempotently load Daria's lesson history + notes from the YAML fixture.

    Idempotent: matching is by (date, instructor, start_time) for sessions and by
    (session_id, skill_id, note) for notes, so re-running never duplicates.
    """
    raw = await asyncio.to_thread(backfill_path.read_text, encoding="utf-8")
    data = yaml.safe_load(raw)
    sessions_repo = SessionRepository(session)
    skills_repo = SkillRepository(session)
    notes_repo = LessonNoteRepository(session)
    all_skills = await skills_repo.all()

    sessions_loaded = 0
    notes_loaded = 0

    for entry in data.get("sessions", []):
        day = date.fromisoformat(str(entry["date"]))
        existing = await sessions_repo.get_by_date(day)
        match = next(
            (
                s
                for s in existing
                if s.instructor == entry.get("instructor") and s.start_time == entry.get("start")
            ),
            None,
        )
        if match is not None:
            session_model = match
        else:
            session_model = await sessions_repo.create(
                date=day,
                start_time=entry.get("start"),
                end_time=entry.get("end"),
                instructor=entry.get("instructor"),
                lesson_type=entry.get("lesson_type", "rijles"),
                status=entry.get("status", "completed"),
                source="manual",
            )
            sessions_loaded += 1

        for note_block in data.get("notes", []):
            if note_block["session_date"] != day:
                continue
            for item in note_block.get("items", []):
                skill = fuzzy_match_skill(item["skill"], all_skills)
                skill_id = skill.id if skill else None
                if await notes_repo.exists(session_model.id, skill_id, item["note"]):
                    continue
                await notes_repo.create(
                    session_id=session_model.id,
                    skill_id=skill_id,
                    note=item["note"],
                    assessment=item.get("assessment"),
                )
                notes_loaded += 1

    await session.commit()
    log.info("backfill.loaded", sessions=sessions_loaded, notes=notes_loaded)
    return {"sessions_loaded": sessions_loaded, "notes_loaded": notes_loaded}
