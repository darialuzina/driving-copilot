"""driving copilot phase 1 schema

Revision ID: 0002_driving_phase1
Revises:
Create Date: 2026-08-06 22:30:00.000000

Creates the driving-copilot tables (sessions, skills, lesson_notes, audit_log)
and seeds the CBR skills matrix as reference data.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from app.db.seed import SKILLS

revision: str = "0002_driving_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.String(length=5), nullable=True),
        sa.Column("end_time", sa.String(length=5), nullable=True),
        sa.Column("instructor", sa.String(length=100), nullable=True),
        sa.Column("lesson_type", sa.String(length=20), nullable=False, server_default="rijles"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="scheduled"),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("email_uid", sa.String(length=200), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("email_uid", name="uq_sessions_email_uid"),
    )
    op.create_index("ix_sessions_date", "sessions", ["date"])

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("name_nl", sa.String(length=80), nullable=True),
        sa.Column("exam_relevant", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    op.create_table(
        "lesson_notes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("session_id", sa.Integer(), sa.ForeignKey("sessions.id"), nullable=False),
        sa.Column("skill_id", sa.Integer(), sa.ForeignKey("skills.id"), nullable=True),
        sa.Column("note", sa.String(length=2000), nullable=False),
        sa.Column("assessment", sa.String(length=20), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_lesson_notes_session_id", "lesson_notes", ["session_id"])
    op.create_index("ix_lesson_notes_skill_id", "lesson_notes", ["skill_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("payload", JSONB(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_audit_log_idempotency_key", "audit_log", ["idempotency_key"])

    skills_table = sa.table(
        "skills",
        sa.Column("category", sa.String),
        sa.Column("name", sa.String),
        sa.Column("name_nl", sa.String),
        sa.Column("exam_relevant", sa.Boolean),
    )
    op.bulk_insert(skills_table, SKILLS)


def downgrade() -> None:
    op.drop_index("ix_audit_log_idempotency_key", table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("ix_lesson_notes_skill_id", table_name="lesson_notes")
    op.drop_index("ix_lesson_notes_session_id", table_name="lesson_notes")
    op.drop_table("lesson_notes")
    op.drop_index("ix_sessions_date", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("skills")
