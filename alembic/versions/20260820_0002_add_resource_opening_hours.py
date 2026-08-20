"""add resource opening hours

Revision ID: 20260820_0002
Revises: 20260728_0001
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260820_0002"
down_revision: str | None = "20260728_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("resources", sa.Column("opening_time", sa.Time(), nullable=True))
    op.add_column("resources", sa.Column("closing_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("resources", "closing_time")
    op.drop_column("resources", "opening_time")
