from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonNoteModel, SessionModel, SkillModel


@dataclass(frozen=True)
class NoteWithContext:
    """A lesson note joined with its session date and skill identity.

    Used by the read tools (get_skill_progress, get_gap_analysis, get_notes) to feed
    the semantic layer without re-querying per note.
    """

    note_id: int
    session_id: int
    session_date: date
    skill_id: int | None
    skill_name: str | None
    skill_name_nl: str | None
    category: str | None
    assessment: str | None
    note: str
    created_at_iso: str | None


class LessonNoteRepository:
    """Async access to the lesson_notes table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        session_id: int,
        skill_id: int | None,
        note: str,
        assessment: str | None,
    ) -> LessonNoteModel:
        model = LessonNoteModel(
            session_id=session_id,
            skill_id=skill_id,
            note=note,
            assessment=assessment,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def exists(self, session_id: int, skill_id: int | None, note: str) -> bool:
        stmt = select(LessonNoteModel.id).where(
            LessonNoteModel.session_id == session_id,
            LessonNoteModel.skill_id.is_(skill_id)
            if skill_id is None
            else LessonNoteModel.skill_id == skill_id,
            LessonNoteModel.note == note,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first() is not None

    async def all_with_session_dates(self) -> list[NoteWithContext]:
        """Every note joined with its session date and skill, ordered chronologically.

        Ordered by session date then note id so the semantic layer can take the last
        N assessments per skill. The dataset is small (Daria's lessons); loading all
        notes in one query is the simplest correct v1 approach.
        """
        stmt = (
            select(
                LessonNoteModel.id.label("note_id"),
                LessonNoteModel.session_id,
                SessionModel.date.label("session_date"),
                LessonNoteModel.skill_id,
                SkillModel.name.label("skill_name"),
                SkillModel.name_nl.label("skill_name_nl"),
                SkillModel.category.label("category"),
                LessonNoteModel.assessment,
                LessonNoteModel.note,
                LessonNoteModel.created_at,
            )
            .join(SessionModel, LessonNoteModel.session_id == SessionModel.id)
            .outerjoin(SkillModel, LessonNoteModel.skill_id == SkillModel.id)
            .order_by(SessionModel.date, LessonNoteModel.id)
        )
        result = await self._session.execute(stmt)
        rows = result.all()
        return [
            NoteWithContext(
                note_id=r.note_id,
                session_id=r.session_id,
                session_date=r.session_date,
                skill_id=r.skill_id,
                skill_name=r.skill_name,
                skill_name_nl=r.skill_name_nl,
                category=r.category,
                assessment=r.assessment,
                note=r.note,
                created_at_iso=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ]
