from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SkillModel


class SkillRepository:
    """Async access to the skills table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def all(self) -> list[SkillModel]:
        stmt = select(SkillModel).order_by(SkillModel.id)
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def get(self, skill_id: int) -> SkillModel | None:
        return await self._session.get(SkillModel, skill_id)
