"""Pydantic API schemas (request/response models). Kept minimal for Phase 0."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from trip_planner.models import PlaceType


class PlaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    name_local: str | None = None
    type: PlaceType
    subtype: str | None = None
    country: str | None = None
    city: str | None = None
    area: str | None = None
    address: str | None = None
    price_level: int | None = None
    rating: float | None = None
