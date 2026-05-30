"""Interim read-only plan viewer at GET /plan (the Phase-5 PWA replaces this)."""

from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select
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
    by_stop: dict[int, list[Place]] = defaultdict(list)
    for place in places:
        stop_id = (place.tags or {}).get("stop_id")
        if stop_id is not None:
            by_stop[stop_id].append(place)
    return HTMLResponse(render_plan(trip, by_stop))
