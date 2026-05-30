"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-30
"""

from __future__ import annotations

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> tuple[sa.Column, sa.Column]:
    """Fresh created_at/updated_at columns (Column objects cannot be shared across tables)."""
    return (
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")

    op.create_table(
        "source",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("kind", sa.String(length=64)),
        sa.Column("language", sa.String(length=16)),
        sa.Column("country", sa.String(length=8)),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("trust_score", sa.Float()),
        sa.Column("discovered_via", sa.String(length=255)),
        sa.Column("last_scraped_at", sa.DateTime(timezone=True)),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
        sa.UniqueConstraint("url", name="uq_source_url"),
    )

    op.create_table(
        "place",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("name_local", sa.String(length=512)),
        sa.Column("description", sa.Text()),
        sa.Column(
            "type",
            sa.Enum("restaurant", "activity", "hotel", "other", name="place_type"),
            nullable=False,
        ),
        sa.Column("subtype", sa.String(length=128)),
        sa.Column("country", sa.String(length=8)),
        sa.Column("city", sa.String(length=128)),
        sa.Column("area", sa.String(length=128)),
        sa.Column("address", sa.String(length=512)),
        sa.Column(
            "location",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
        sa.Column("google_place_id", sa.String(length=255)),
        sa.Column("price_level", sa.Integer()),
        sa.Column("rating", sa.Float()),
        sa.Column("geocode_source", sa.String(length=32)),
        sa.Column("geocode_confidence", sa.Float()),
        sa.Column("tags", postgresql.JSONB()),
        sa.Column("extra", postgresql.JSONB()),
        *_timestamps(),
    )
    op.create_index("ix_place_google_place_id", "place", ["google_place_id"])
    op.create_index("ix_place_location", "place", ["location"], postgresql_using="gist")

    op.create_table(
        "place_mention",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "source_id",
            sa.Integer(),
            sa.ForeignKey("source.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(length=1024)),
        sa.Column("snippet", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_place_mention_place_id", "place_mention", ["place_id"])
    op.create_index("ix_place_mention_source_id", "place_mention", ["source_id"])

    op.create_table(
        "trip",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_date", sa.Date()),
        sa.Column("end_date", sa.Date()),
        sa.Column("travelers", postgresql.JSONB()),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )

    op.create_table(
        "stop",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trip_id", sa.Integer(), sa.ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("country", sa.String(length=8)),
        sa.Column("region", sa.String(length=128)),
        sa.Column("area", sa.String(length=128)),
        sa.Column("arrival_date", sa.Date()),
        sa.Column("departure_date", sa.Date()),
        sa.Column("nights", sa.Integer()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("hotel_place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="SET NULL")),
        sa.Column(
            "centroid",
            geoalchemy2.Geometry(geometry_type="POINT", srid=4326, spatial_index=False),
        ),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_stop_trip_id", "stop", ["trip_id"])
    op.create_index("ix_stop_centroid", "stop", ["centroid"], postgresql_using="gist")

    op.create_table(
        "day",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "trip_id", sa.Integer(), sa.ForeignKey("trip.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("stop_id", sa.Integer(), sa.ForeignKey("stop.id", ondelete="SET NULL")),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("title", sa.String(length=255)),
        sa.Column("summary", sa.Text()),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_day_trip_id", "day", ["trip_id"])
    op.create_index("ix_day_stop_id", "day", ["stop_id"])

    op.create_table(
        "itinerary_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "day_id", sa.Integer(), sa.ForeignKey("day.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("place_id", sa.Integer(), sa.ForeignKey("place.id", ondelete="SET NULL")),
        sa.Column(
            "kind",
            sa.Enum("meal", "activity", "transit", "lodging", "free", name="item_kind"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=512)),
        sa.Column("start_time", sa.Time()),
        sa.Column("end_time", sa.Time()),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("transit_mode", sa.String(length=32)),
        sa.Column("transit_duration_min", sa.Integer()),
        sa.Column("notes", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_itinerary_item_day_id", "itinerary_item", ["day_id"])
    op.create_index("ix_itinerary_item_place_id", "itinerary_item", ["place_id"])

    op.create_table(
        "edit_log",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.Integer()),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("diff", postgresql.JSONB()),
        sa.Column("actor", sa.String(length=64)),
        sa.Column("origin", sa.String(length=16)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "document",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("source.id", ondelete="SET NULL")),
        sa.Column("url", sa.String(length=1024), nullable=False),
        sa.Column("canonical_url", sa.String(length=1024)),
        sa.Column("http_status", sa.Integer()),
        sa.Column("fetched_at", sa.DateTime(timezone=True)),
        sa.Column("content_hash", sa.String(length=64)),
        sa.Column("raw_path", sa.String(length=512)),
        sa.Column("title", sa.String(length=512)),
        sa.Column("extracted_text", sa.Text()),
        sa.Column("language", sa.String(length=16)),
        sa.Column("word_count", sa.Integer()),
        sa.Column("error", sa.Text()),
        *_timestamps(),
    )
    op.create_index("ix_document_source_id", "document", ["source_id"])
    op.create_index("ix_document_content_hash", "document", ["content_hash"])


def downgrade() -> None:
    op.drop_table("document")
    op.drop_table("edit_log")
    op.drop_table("itinerary_item")
    op.drop_table("day")
    op.drop_table("stop")
    op.drop_table("trip")
    op.drop_table("place_mention")
    op.drop_index("ix_place_location", table_name="place")
    op.drop_table("place")
    op.drop_table("source")
    op.execute("DROP TYPE IF EXISTS item_kind")
    op.execute("DROP TYPE IF EXISTS place_type")
