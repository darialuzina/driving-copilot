from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import LinkResponse
from app.config import get_settings
from app.db.session import provide_session
from app.domain.link import Link
from app.repositories.link_repository import LinkRepository
from app.services.link_service import LinkService

SessionDep = Annotated[AsyncSession, Depends(provide_session)]


async def get_link_service(session: SessionDep) -> LinkService:
    return LinkService(LinkRepository(session), code_length=get_settings().code_length)


ServiceDep = Annotated[LinkService, Depends(get_link_service)]


def to_response(link: Link) -> LinkResponse:
    if link.id is None:
        raise ValueError("cannot serialize an unsaved link")
    base = get_settings().base_url.rstrip("/")
    now = datetime.now(UTC)
    return LinkResponse(
        id=link.id,
        short_code=link.short_code.value,
        target_url=link.target_url.value,
        short_url=f"{base}/{link.short_code.value}",
        status=link.status(now).value,
        clicks=link.clicks,
        created_at=link.created_at,
        expires_at=link.expires_at,
        disabled=link.disabled,
    )
