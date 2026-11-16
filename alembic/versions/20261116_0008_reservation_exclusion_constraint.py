"""prevent overlapping reservations with an exclusion constraint

Revision ID: 20261116_0008
Revises: 20261116_0007
Create Date: 2026-11-16
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261116_0008"
down_revision: str | None = "20261116_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Impide superponer reservas no canceladas del mismo recurso.

    La columna `period` es calculada por PostgreSQL con el rango semiabierto
    [inicio, fin), de modo que dos reservas consecutivas puedan tocarse en el
    extremo. La extensión btree_gist hace que el recurso (un entero) pueda
    participar de un índice GiST.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    op.add_column(
        "reservations",
        sa.Column(
            "period",
            postgresql.TSTZRANGE(),
            sa.Computed("tstzrange(start_at, end_at, '[)')", persisted=True),
        ),
    )
    op.create_exclude_constraint(
        "reservations_no_overlapping_periods",
        "reservations",
        ("resource_id", "="),
        ("period", "&&"),
        where=sa.text("status <> 'cancelled'"),
        using="gist",
    )


def downgrade() -> None:
    op.drop_constraint(
        "reservations_no_overlapping_periods", "reservations", type_="exclude"
    )
    op.drop_column("reservations", "period")
