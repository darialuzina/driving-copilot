from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import LessonNoteModel, SessionModel


class SessionRepository:
    """Async access to the sessions table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_upcoming(self, today: date, days_ahead: int) -> list[SessionModel]:
        horizon = date.fromordinal(today.toordinal() + days_ahead)
        stmt = (
            select(SessionModel)
            .where(SessionModel.date >= today)
            .where(SessionModel.date <= horizon)
            .where(SessionModel.status == "scheduled")
            .order_by(SessionModel.date, SessionModel.start_time)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_history(self, today: date, limit: int) -> list[SessionModel]:
        stmt = (
            select(SessionModel)
            .where(SessionModel.date < today)
            .order_by(SessionModel.date.desc(), SessionModel.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_date(self, day: date) -> list[SessionModel]:
        stmt = select(SessionModel).where(SessionModel.date == day).order_by(SessionModel.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_email_uid(self, email_uid: str) -> SessionModel | None:
        stmt = select(SessionModel).where(SessionModel.email_uid == email_uid)
        result = await self._session.execute(stmt)
        return result.scalars().first()

    async def create(
        self,
        *,
        date: date,
        start_time: str | None = None,
        end_time: str | None = None,
        instructor: str | None = None,
        lesson_type: str = "rijles",
        status: str = "completed",
        source: str = "manual",
        email_uid: str | None = None,
    ) -> SessionModel:
        model = SessionModel(
            date=date,
            start_time=start_time,
            end_time=end_time,
            instructor=instructor,
            lesson_type=lesson_type,
            status=status,
            source=source,
            email_uid=email_uid,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def notes_for(self, session_id: int) -> list[LessonNoteModel]:
        stmt = (
            select(LessonNoteModel)
            .where(LessonNoteModel.session_id == session_id)
            .order_by(LessonNoteModel.id)
        )
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def count_scheduled_from(
        self, today: date, until: date | None = None
    ) -> int:
        """Count scheduled sessions with date >= today (and <= until if given).

        Used by pace() to compute lessons remaining before the exam date. When no
        exam date is set, counts all upcoming scheduled lessons.
        """
        stmt = (
            select(SessionModel.id)
            .where(SessionModel.date >= today)
            .where(SessionModel.status == "scheduled")
        )
        if until is not None:
            stmt = stmt.where(SessionModel.date <= until)
        result = await self._session.execute(stmt)
        return len(result.all())
