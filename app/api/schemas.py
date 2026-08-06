from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class CreateLinkRequest(BaseModel):
    url: str
    ttl_seconds: int | None = None
    custom_code: str | None = None


class LinkResponse(BaseModel):
    id: int
    short_code: str
    target_url: str
    short_url: str
    status: str
    clicks: int
    created_at: datetime
    expires_at: datetime | None
    disabled: bool
