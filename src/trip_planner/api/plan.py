"""Interim read-only plan viewer at GET /plan (the Phase-5 PWA replaces this)."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.db import SessionDep
from trip_planner.models import Day, Stop, Trip
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
    return HTMLResponse(render_plan(trip))
