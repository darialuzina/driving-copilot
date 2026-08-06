from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLogModel


class AuditLogRepository:
    """Async access to the audit_log table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self, *, action: str, payload: dict[str, object], idempotency_key: str | None
    ) -> AuditLogModel:
        model = AuditLogModel(
            action=action,
            payload=json.loads(json.dumps(payload, default=str)),
            idempotency_key=idempotency_key,
        )
        self._session.add(model)
        await self._session.flush()
        return model

    async def get_by_idempotency_key(self, key: str) -> AuditLogModel | None:
        stmt = select(AuditLogModel).where(AuditLogModel.idempotency_key == key)
        result = await self._session.execute(stmt)
        return result.scalars().first()
