from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select, update

from app.db.models import LinkModel
from app.domain.link import Link
from app.domain.value_objects import ShortCode, TargetUrl

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


def _to_domain(row: LinkModel) -> Link:
    return Link(
        id=row.id,
        short_code=ShortCode(row.short_code),
        target_url=TargetUrl(row.target_url),
        created_at=row.created_at,
        expires_at=row.expires_at,
        clicks=row.clicks,
        disabled=row.disabled,
    )


class LinkRepository:
    """Доступ к таблице links. Принимает и возвращает доменные объекты, скрывая ORM."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, link: Link) -> Link:
        row = LinkModel(
            short_code=link.short_code.value,
            target_url=link.target_url.value,
            created_at=link.created_at,
            expires_at=link.expires_at,
            clicks=link.clicks,
            disabled=link.disabled,
        )
        self._session.add(row)
        await self._session.flush()
        return _to_domain(row)

    async def get_by_code(self, short_code: str) -> Link | None:
        # Учебный антипаттерн (Секция 12): SELECT всей таблицы + поиск в Python.
        # Индекс на short_code не используется. Под нагрузкой RPS падает —
        # фикс: where(LinkModel.short_code == short_code) + scalar_one_or_none().
        rows = (await self._session.execute(select(LinkModel))).scalars().all()
        for row in rows:
            if row.short_code == short_code:
                return _to_domain(row)
        return None

    async def list_all(self, limit: int = 100) -> list[Link]:
        stmt = select(LinkModel).order_by(LinkModel.id.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [_to_domain(row) for row in rows]

    async def update(self, link: Link) -> Link:
        """Сохраняет изменяемые поля сущности (clicks, disabled) по short_code."""
        stmt = (
            update(LinkModel)
            .where(LinkModel.short_code == link.short_code.value)
            .values(clicks=link.clicks, disabled=link.disabled)
        )
        await self._session.execute(stmt)
        return link
