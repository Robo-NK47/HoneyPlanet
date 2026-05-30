"""per-day & per-item spending estimates (budget expert)

Revision ID: 0006_spending
Revises: 0005_event
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_spending"
down_revision: str | None = "0005_event"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("day", sa.Column("est_cost", sa.Integer()))
    op.add_column("day", sa.Column("cost_breakdown", postgresql.JSONB(astext_type=sa.Text())))
    op.add_column("itinerary_item", sa.Column("est_cost", sa.Integer()))


def downgrade() -> None:
    op.drop_column("itinerary_item", "est_cost")
    op.drop_column("day", "cost_breakdown")
    op.drop_column("day", "est_cost")
