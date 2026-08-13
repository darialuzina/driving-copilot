"""drive-7: add braking control and acceleration skills

Revision ID: 0003_drive7_skills
Revises: 0002_driving_phase1
Create Date: 2026-08-13 16:00:00.000000

Adds two Vehicle-control skills Daria's instructor treats as distinct
competencies ("remmen" / braking control and "versnellen" / acceleration) so
free-text lesson notes can match them instead of falling through to general
notes. Reference-data insert only — no schema change.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_drive7_skills"
down_revision: str | None = "0002_driving_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NEW_SKILLS = [
    {
        "category": "Vehicle control",
        "name": "braking control",
        "name_nl": "remmen",
        "exam_relevant": True,
    },
    {
        "category": "Vehicle control",
        "name": "acceleration",
        "name_nl": "versnellen",
        "exam_relevant": True,
    },
]


def upgrade() -> None:
    skills_table = sa.table(
        "skills",
        sa.Column("category", sa.String),
        sa.Column("name", sa.String),
        sa.Column("name_nl", sa.String),
        sa.Column("exam_relevant", sa.Boolean),
    )
    op.bulk_insert(skills_table, _NEW_SKILLS)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM skills WHERE name IN ('braking control', 'acceleration')"
        )
    )
