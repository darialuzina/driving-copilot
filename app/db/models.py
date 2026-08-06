from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SessionModel(Base):
    """A driving lesson, from an On My Way email or a manual entry."""

    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    instructor: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lesson_type: Mapped[str] = mapped_column(String(20), default="rijles")  # rijles|proefles|exam
    status: Mapped[str] = mapped_column(
        String(20), default="scheduled"
    )  # scheduled|completed|cancelled
    source: Mapped[str] = mapped_column(String(20), default="manual")  # email|manual
    email_uid: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SkillModel(Base):
    """The CBR competency matrix (seeded)."""

    __tablename__ = "skills"

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[str] = mapped_column(String(60))
    name: Mapped[str] = mapped_column(String(80))
    name_nl: Mapped[str | None] = mapped_column(String(80), nullable=True)
    exam_relevant: Mapped[bool] = mapped_column(Boolean, default=True)


class LessonNoteModel(Base):
    """Daria's observation on a lesson, optionally linked to a skill."""

    __tablename__ = "lesson_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id"))
    skill_id: Mapped[int | None] = mapped_column(ForeignKey("skills.id"), nullable=True)
    note: Mapped[str] = mapped_column(String(2000))
    assessment: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # good|ok|needs_attention|not_practiced
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLogModel(Base):
    """Every write: who/what/when. Idempotency key for safe retries."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    idempotency_key: Mapped[str | None] = mapped_column(String(120), index=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
