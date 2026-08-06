from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        # Учебно заужаем пул (Секция 12): pool_size=5 + max_overflow=5.
        # Под нагрузкой легко упереться в ожидание соединений к Postgres — это одно из
        # узких мест для шага «улучшение производительности».
        _engine = create_async_engine(
            get_settings().database_url, pool_size=5, max_overflow=5, pool_pre_ping=True
        )
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def provide_session() -> AsyncGenerator[AsyncSession]:
    """Зависимость БД: одна сессия на запрос с авто-commit/rollback."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
