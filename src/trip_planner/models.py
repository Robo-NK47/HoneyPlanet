"""ORM models — the system of record for sources, places, and the trip plan.

Hierarchy:
    Trip ──< Stop (meta level: city/region stays) ──< Day ──< ItineraryItem
    Source ──< PlaceMention >── Place   (provenance: which source mentioned a place)
    EditLog                            (audit trail for laptop/phone edits)

Spatial columns use PostGIS POINT geometry (SRID 4326 / WGS84) so the planner can
ask geo questions like "what's within a 10-minute walk of this hotel".
"""

from __future__ import annotations

import enum
from datetime import date, datetime, time

from geoalchemy2 import Geometry
from geoalchemy2.elements import WKBElement
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from trip_planner.db import Base


class PlaceType(enum.StrEnum):
    restaurant = "restaurant"
    activity = "activity"
    hotel = "hotel"
    other = "other"


class ItemKind(enum.StrEnum):
    meal = "meal"
    activity = "activity"
    transit = "transit"
    lodging = "lodging"
    free = "free"


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Source(TimestampMixin, Base):
    """A scraped data source (blog, forum, guide, official site)."""

    __tablename__ = "source"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(1024), nullable=False, unique=True)
    kind: Mapped[str | None] = mapped_column(String(64))  # blog / forum / guide / official
    language: Mapped[str | None] = mapped_column(String(16))  # he / en / ja / th
    country: Mapped[str | None] = mapped_column(String(8))  # jp / th
    is_seed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trust_score: Mapped[float | None] = mapped_column(Float)
    discovered_via: Mapped[str | None] = mapped_column(String(255))
    last_scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)

    mentions: Mapped[list[PlaceMention]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )
    documents: Mapped[list[Document]] = relationship(
        back_populates="source", cascade="all, delete-orphan"
    )


class Place(TimestampMixin, Base):
    """A categorized place: restaurant / activity / hotel / other, with coordinates."""

    __tablename__ = "place"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(512))  # ja / th name for navigation
    description: Mapped[str | None] = mapped_column(Text)
    type: Mapped[PlaceType] = mapped_column(
        Enum(PlaceType, name="place_type"), nullable=False, default=PlaceType.other
    )
    subtype: Mapped[str | None] = mapped_column(String(128))  # ramen / jazz_bar / onsen / temple
    country: Mapped[str | None] = mapped_column(String(8))
    city: Mapped[str | None] = mapped_column(String(128))
    area: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(512))
    location: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )
    google_place_id: Mapped[str | None] = mapped_column(String(255), index=True)
    price_level: Mapped[int | None] = mapped_column(Integer)  # 0–4 (Google scale)
    rating: Mapped[float | None] = mapped_column(Float)
    geocode_source: Mapped[str | None] = mapped_column(String(32))  # nominatim / google / manual
    geocode_confidence: Mapped[float | None] = mapped_column(Float)
    tags: Mapped[dict | None] = mapped_column(JSONB)
    extra: Mapped[dict | None] = mapped_column(JSONB)  # raw payloads, opening hours, etc.

    mentions: Mapped[list[PlaceMention]] = relationship(
        back_populates="place", cascade="all, delete-orphan"
    )


class PlaceMention(TimestampMixin, Base):
    """Provenance link: a source mentioned a place (keeps why/where we found it)."""

    __tablename__ = "place_mention"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    place_id: Mapped[int] = mapped_column(
        ForeignKey("place.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("source.id", ondelete="CASCADE"), nullable=False, index=True
    )
    url: Mapped[str | None] = mapped_column(String(1024))
    snippet: Mapped[str | None] = mapped_column(Text)

    place: Mapped[Place] = relationship(back_populates="mentions")
    source: Mapped[Source] = relationship(back_populates="mentions")


class Trip(TimestampMixin, Base):
    """The honeymoon trip — root of the plan hierarchy."""

    __tablename__ = "trip"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    travelers: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    stops: Mapped[list[Stop]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="Stop.order_index"
    )
    days: Mapped[list[Day]] = relationship(
        back_populates="trip", cascade="all, delete-orphan", order_by="Day.date"
    )


class Stop(TimestampMixin, Base):
    """Meta level: a city/region stay (e.g. Tokyo for 7 nights)."""

    __tablename__ = "stop"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(8))
    region: Mapped[str | None] = mapped_column(String(128))
    area: Mapped[str | None] = mapped_column(String(128))  # preferred neighborhood
    arrival_date: Mapped[date | None] = mapped_column(Date)
    departure_date: Mapped[date | None] = mapped_column(Date)
    nights: Mapped[int | None] = mapped_column(Integer)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hotel_place_id: Mapped[int | None] = mapped_column(ForeignKey("place.id", ondelete="SET NULL"))
    centroid: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )
    notes: Mapped[str | None] = mapped_column(Text)

    trip: Mapped[Trip] = relationship(back_populates="stops")
    hotel: Mapped[Place | None] = relationship()
    days: Mapped[list[Day]] = relationship(back_populates="stop", order_by="Day.date")


class Day(TimestampMixin, Base):
    """Per-day level: one calendar day of the trip."""

    __tablename__ = "day"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trip.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stop_id: Mapped[int | None] = mapped_column(
        ForeignKey("stop.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    est_cost: Mapped[int | None] = mapped_column(Integer)  # budget expert: total spend (NIS) / day
    cost_breakdown: Mapped[dict | None] = mapped_column(
        JSONB
    )  # {lodging, food, transport, activities, other} in NIS

    trip: Mapped[Trip] = relationship(back_populates="days")
    stop: Mapped[Stop | None] = relationship(back_populates="days")
    items: Mapped[list[ItineraryItem]] = relationship(
        back_populates="day", cascade="all, delete-orphan", order_by="ItineraryItem.order_index"
    )


class ItineraryItem(TimestampMixin, Base):
    """A single ordered entry within a day: a meal, activity, transit leg, etc."""

    __tablename__ = "itinerary_item"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day_id: Mapped[int] = mapped_column(
        ForeignKey("day.id", ondelete="CASCADE"), nullable=False, index=True
    )
    place_id: Mapped[int | None] = mapped_column(
        ForeignKey("place.id", ondelete="SET NULL"), index=True
    )
    kind: Mapped[ItemKind] = mapped_column(
        Enum(ItemKind, name="item_kind"), nullable=False, default=ItemKind.activity
    )
    title: Mapped[str | None] = mapped_column(String(512))
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    order_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    transit_mode: Mapped[str | None] = mapped_column(String(128))  # walk / Shinkansen / ferry…
    transit_duration_min: Mapped[int | None] = mapped_column(Integer)
    est_cost: Mapped[int | None] = mapped_column(Integer)  # est. cost (NIS) for this item, 2 pax
    notes: Mapped[str | None] = mapped_column(Text)
    booking_notice: Mapped[str | None] = mapped_column(Text)  # reservations / tickets to book ahead

    day: Mapped[Day] = relationship(back_populates="items")
    place: Mapped[Place | None] = relationship()


class EditLog(Base):
    """Audit trail of changes, tagged by origin (laptop vs phone) for sync debugging."""

    __tablename__ = "edit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[int | None] = mapped_column(Integer)
    action: Mapped[str] = mapped_column(String(16), nullable=False)  # create / update / delete
    diff: Mapped[dict | None] = mapped_column(JSONB)
    actor: Mapped[str | None] = mapped_column(String(64))
    origin: Mapped[str | None] = mapped_column(String(16))  # laptop / phone
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Document(TimestampMixin, Base):
    """A fetched web page: raw HTML cached on disk, main text extracted for later mining."""

    __tablename__ = "document"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int | None] = mapped_column(
        ForeignKey("source.id", ondelete="SET NULL"), index=True
    )
    url: Mapped[str] = mapped_column(String(1024), nullable=False)
    canonical_url: Mapped[str | None] = mapped_column(String(1024))
    http_status: Mapped[int | None] = mapped_column(Integer)
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)  # sha256 hex
    raw_path: Mapped[str | None] = mapped_column(String(512))  # cached HTML, relative to data dir
    title: Mapped[str | None] = mapped_column(String(512))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(16))
    word_count: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)

    source: Mapped[Source | None] = relationship(back_populates="documents")


class Task(TimestampMixin, Base):
    """An actionable trip to-do (book a hotel, reserve a restaurant, buy train tickets)."""

    __tablename__ = "task"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    due_date: Mapped[date | None] = mapped_column(Date)  # categorize by date
    importance: Mapped[str] = mapped_column(String(16), nullable=False, default="medium")
    done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class Event(TimestampMixin, Base):
    """A festival or seasonal event during the trip (matsuri, illumination, market)."""

    __tablename__ = "event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    name_local: Mapped[str | None] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(32))  # festival/seasonal/illumination/...
    city: Mapped[str | None] = mapped_column(String(128))
    country: Mapped[str | None] = mapped_column(String(8))
    venue: Mapped[str | None] = mapped_column(String(256))
    location: Mapped[WKBElement | None] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326, spatial_index=True)
    )
    start_date: Mapped[date | None] = mapped_column(Date)
    end_date: Mapped[date | None] = mapped_column(Date)
    url: Mapped[str | None] = mapped_column(String(1024))
    notes: Mapped[str | None] = mapped_column(Text)
