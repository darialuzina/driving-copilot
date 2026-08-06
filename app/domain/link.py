from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from typing import Self

from app.domain.value_objects import ShortCode, TargetUrl


class LinkStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class Link:
    """Доменная сущность короткой ссылки. Хранит правила и поведение, без привязки к БД."""

    short_code: ShortCode
    target_url: TargetUrl
    created_at: datetime
    expires_at: datetime | None = None
    clicks: int = 0
    disabled: bool = False
    id: int | None = None

    def status(self, now: datetime) -> LinkStatus:
        """Статус ссылки на момент `now`."""
        if self.disabled:
            return LinkStatus.DISABLED
        if self.expires_at is not None and now >= self.expires_at:
            return LinkStatus.EXPIRED
        return LinkStatus.ACTIVE

    def is_active(self, now: datetime) -> bool:
        return self.status(now) is LinkStatus.ACTIVE

    def with_click(self) -> Self:
        """Возвращает копию с увеличенным счётчиком переходов (сущность неизменяема)."""
        return replace(self, clicks=self.clicks + 1)

    def disable(self) -> Self:
        """Возвращает отключённую копию ссылки."""
        return replace(self, disabled=True)
