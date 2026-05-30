"""widen itinerary_item.transit_mode to 128

Revision ID: 0003_widen_transit_mode
Revises: 0002_booking_notice
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_widen_transit_mode"
down_revision: str | None = "0002_booking_notice"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "itinerary_item",
        "transit_mode",
        existing_type=sa.String(length=32),
        type_=sa.String(length=128),
    )


def downgrade() -> None:
    op.alter_column(
        "itinerary_item",
        "transit_mode",
        existing_type=sa.String(length=128),
        type_=sa.String(length=32),
    )
