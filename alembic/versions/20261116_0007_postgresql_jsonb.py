"""convert resource json columns to jsonb

Revision ID: 20261116_0007
Revises: 20261103_0006
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261116_0007"
down_revision: str | None = "20261103_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """En PostgreSQL los JSON pasan a JSONB, que admite índices y es más rápido."""
    op.alter_column(
        "resources",
        "closed_dates",
        type_=postgresql.JSONB(),
        existing_type=sa.JSON(),
        postgresql_using="closed_dates::jsonb",
    )
    op.alter_column(
        "resources",
        "closed_weekdays",
        type_=postgresql.JSONB(),
        existing_type=sa.JSON(),
        postgresql_using="closed_weekdays::jsonb",
    )


def downgrade() -> None:
    op.alter_column(
        "resources",
        "closed_weekdays",
        type_=sa.JSON(),
        existing_type=postgresql.JSONB(),
        postgresql_using="closed_weekdays::json",
    )
    op.alter_column(
        "resources",
        "closed_dates",
        type_=sa.JSON(),
        existing_type=postgresql.JSONB(),
        postgresql_using="closed_dates::json",
    )
