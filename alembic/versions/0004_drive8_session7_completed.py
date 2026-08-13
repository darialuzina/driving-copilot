"""drive-8: mark session 7 completed (week-one data fix)

Revision ID: 0004_drive8_session7_completed
Revises: 0003_drive7_skills
Create Date: 2026-08-13 17:00:00.000000

Production week-one data fix: session 7 is a lesson Daria practiced and logged
notes against on 2026-08-13, but its row is still status='scheduled'. pace()
therefore counts the finished lesson as "1 lesson remaining" against the exam
date. Flip it to 'completed' to match reality. This is a one-row data fix, not a
schema change; on a clean DB the UPDATE affects 0 rows (idempotent).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text

revision: str = "0004_drive8_session7_completed"
down_revision: str | None = "0003_drive7_skills"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        text("UPDATE sessions SET status = 'completed' WHERE id = 7")
    )


def downgrade() -> None:
    # Revert to the (buggy) pre-fix state for reproducibility. On a clean DB this
    # affects 0 rows; it only matters on the production DB this was applied to.
    op.execute(
        text("UPDATE sessions SET status = 'scheduled' WHERE id = 7")
    )
