"""booking_notice on itinerary_item

Revision ID: 0002_booking_notice
Revises: 0001_initial
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_booking_notice"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("itinerary_item", sa.Column("booking_notice", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("itinerary_item", "booking_notice")
