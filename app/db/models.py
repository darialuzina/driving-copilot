from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkModel(Base):
    """ORM-модель таблицы links. Маппинг в доменную сущность — в repository."""

    __tablename__ = "links"

    id: Mapped[int] = mapped_column(primary_key=True)
    short_code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    target_url: Mapped[str] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
