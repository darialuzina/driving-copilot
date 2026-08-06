from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.domain.errors import (
    LinkDisabledError,
    LinkExpiredError,
    LinkNotFoundError,
    ShortCodeTakenError,
)
from app.domain.link import Link, LinkStatus
from app.domain.value_objects import CODE_ALPHABET, ShortCode, TargetUrl


class LinkRepositoryProtocol(Protocol):
    """Контракт репозитория. Позволяет подменять реализацию в unit-тестах."""

    async def add(self, link: Link) -> Link: ...
    async def get_by_code(self, short_code: str) -> Link | None: ...
    async def list_all(self, limit: int = 100) -> list[Link]: ...
    async def update(self, link: Link) -> Link: ...


class LinkService:
    """Бизнес-логика ссылок: создание с TTL, резолв со статусом, счётчик переходов, отключение."""

    def __init__(self, repository: LinkRepositoryProtocol, code_length: int = 7) -> None:
        self._repository = repository
        self._code_length = code_length

    def _generate_code(self) -> ShortCode:
        return ShortCode("".join(secrets.choice(CODE_ALPHABET) for _ in range(self._code_length)))

    async def create_link(
        self,
        target_url: str,
        ttl_seconds: int | None = None,
        custom_code: str | None = None,
    ) -> Link:
        now = datetime.now(UTC)
        if custom_code is not None:
            code = ShortCode(custom_code)
            if await self._repository.get_by_code(code.value) is not None:
                raise ShortCodeTakenError(code.value)
        else:
            code = self._generate_code()
        expires_at = (
            now + timedelta(seconds=ttl_seconds) if ttl_seconds and ttl_seconds > 0 else None
        )
        link = Link(
            short_code=code,
            target_url=TargetUrl(target_url),
            created_at=now,
            expires_at=expires_at,
        )
        return await self._repository.add(link)

    async def get_link(self, short_code: str) -> Link:
        link = await self._repository.get_by_code(short_code)
        if link is None:
            raise LinkNotFoundError(short_code)
        return link

    async def list_links(self, limit: int = 100) -> list[Link]:
        return await self._repository.list_all(limit)

    async def resolve(self, short_code: str) -> Link:
        """Резолв для редиректа: проверяет статус и инкрементит счётчик у активной ссылки."""
        link = await self.get_link(short_code)
        status = link.status(datetime.now(UTC))
        if status is LinkStatus.EXPIRED:
            raise LinkExpiredError(short_code)
        if status is LinkStatus.DISABLED:
            raise LinkDisabledError(short_code)
        return await self._repository.update(link.with_click())

    async def disable_link(self, short_code: str) -> Link:
        link = await self.get_link(short_code)
        return await self._repository.update(link.disable())
