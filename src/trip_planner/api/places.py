"""Basic Place read endpoints — establishes the DB-access pattern for later phases."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from trip_planner.db import SessionDep
from trip_planner.models import Place
from trip_planner.schemas import PlaceOut

router = APIRouter(prefix="/places", tags=["places"])


@router.get("", response_model=list[PlaceOut])
async def list_places(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Place]:
    result = await session.execute(select(Place).order_by(Place.id).limit(limit).offset(offset))
    return list(result.scalars().all())


@router.get("/{place_id}", response_model=PlaceOut)
async def get_place(place_id: int, session: SessionDep) -> Place:
    place = await session.get(Place, place_id)
    if place is None:
        raise HTTPException(status_code=404, detail="Place not found")
    return place
