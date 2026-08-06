from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonNoteModel


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
        from sqlalchemy import select

        stmt = select(LessonNoteModel.id).where(
            LessonNoteModel.session_id == session_id,
            LessonNoteModel.skill_id.is_(skill_id)
            if skill_id is None
            else LessonNoteModel.skill_id == skill_id,
            LessonNoteModel.note == note,
        )
        result = await self._session.execute(stmt)
        return result.scalars().first() is not None
