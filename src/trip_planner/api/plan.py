"""Interim read-only plan viewer at GET /plan (the Phase-5 PWA replaces this)."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.db import SessionDep
from trip_planner.models import Day, Place, Stop, Trip
from trip_planner.web import render_plan

router = APIRouter(tags=["plan"])


@router.get("/plan", response_class=HTMLResponse)
async def plan_view(session: SessionDep) -> HTMLResponse:
    stmt = (
        select(Trip)
        .options(selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items))
        .order_by(Trip.id)
        .limit(1)
    )
    trip = (await session.execute(stmt)).scalars().first()
    places = (await session.execute(select(Place))).scalars().all()
    coord_rows = (
        await session.execute(
            select(Place.id, func.ST_Y(Place.location), func.ST_X(Place.location)).where(
                Place.location.isnot(None)
            )
        )
    ).all()
    coords = {pid: (lat, lng) for pid, lat, lng in coord_rows}

    by_stop: dict[int, list[Place]] = defaultdict(list)
    markers: list[dict] = []
    for place in places:
        stop_id = (place.tags or {}).get("stop_id")
        if stop_id is not None:
            by_stop[stop_id].append(place)
        if place.id in coords:
            lat, lng = coords[place.id]
            tags = place.tags or {}
            markers.append(
                {
                    "id": place.id,
                    "lat": lat,
                    "lng": lng,
                    "name": place.name,
                    "cat": tags.get("category") or place.subtype or "other",
                    "url": tags.get("website") or tags.get("maps_uri") or "#",
                    "rating": place.rating,
                }
            )
    return HTMLResponse(render_plan(trip, by_stop, markers))
