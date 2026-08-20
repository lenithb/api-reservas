"""add resource closed dates

Revision ID: 20260820_0003
Revises: 20260820_0002
Create Date: 2026-08-20
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "20260820_0003"
down_revision: str | None = "20260820_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resources",
        sa.Column(
            "closed_dates",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("resources", "closed_dates")
