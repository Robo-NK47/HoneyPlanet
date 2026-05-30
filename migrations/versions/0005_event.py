"""festival & seasonal event layer

Revision ID: 0005_event
Revises: 0004_task
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op

revision: str = "0005_event"
down_revision: str | None = "0004_task"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("name_local", sa.String(length=512)),
        sa.Column("description", sa.Text()),
        sa.Column("category", sa.String(length=32)),
        sa.Column("city", sa.String(length=128)),
        sa.Column("country", sa.String(length=8)),
        sa.Column("venue", sa.String(length=256)),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("url", sa.String(length=1024)),
        sa.Column("notes", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_event_location", "event", ["location"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("ix_event_location", table_name="event")
    op.drop_table("event")
