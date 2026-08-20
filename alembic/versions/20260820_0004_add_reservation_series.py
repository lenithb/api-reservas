"""add reservation series

Revision ID: 20260820_0004
Revises: 20260820_0003
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260820_0004"
down_revision: str | None = "20260820_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reservations", sa.Column("series_id", sa.String(length=36), nullable=True)
    )
    op.create_index("ix_reservations_series_id", "reservations", ["series_id"])


def downgrade() -> None:
    op.drop_index("ix_reservations_series_id", table_name="reservations")
    op.drop_column("reservations", "series_id")
