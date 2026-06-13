"""Interim read-only plan viewer at GET /plan (the Phase-5 PWA replaces this)."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.api.auth import auth_enabled, is_authed
from trip_planner.db import SessionDep
from trip_planner.models import Day, Event, Place, Stop, Trip
from trip_planner.plan.costs import build_budget
from trip_planner.web import render_plan

router = APIRouter(tags=["plan"])

TOTAL_BUDGET_NIS = 75_000  # raised from 50k after the real hotels were booked (~₪44k lodging)


def _fmt_dates(start: date | None, end: date | None) -> str:
    if not start:
        return ""
    if not end or end == start:
        return start.strftime("%b %d")
    return f"{start.strftime('%b %d')} – {end.strftime('%b %d')}"


@router.get("/plan", response_class=HTMLResponse)
async def plan_view(request: Request, session: SessionDep) -> Response:
    if auth_enabled() and not is_authed(request):
        return RedirectResponse("/login", status_code=303)
    stmt = (
        select(Trip)
        .options(
            selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items),
            selectinload(Trip.stops).selectinload(Stop.hotel),
        )
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

    events = (await session.execute(select(Event))).scalars().all()
    ecoord_rows = (
        await session.execute(
            select(Event.id, func.ST_Y(Event.location), func.ST_X(Event.location)).where(
                Event.location.isnot(None)
            )
        )
    ).all()
    ecoords = {eid: (lat, lng) for eid, lat, lng in ecoord_rows}

    event_markers: list[dict] = []
    all_events: list[dict] = []
    for ev in sorted(events, key=lambda e: (e.start_date or date.max)):
        dates = _fmt_dates(ev.start_date, ev.end_date)
        all_events.append(
            {
                "name": ev.name,
                "city": ev.city,
                "category": ev.category,
                "dates": dates,
                "url": ev.url,
            }
        )
        if ev.id in ecoords:
            lat, lng = ecoords[ev.id]
            event_markers.append(
                {
                    "lat": lat,
                    "lng": lng,
                    "name": ev.name,
                    "dates": dates,
                    "url": ev.url or "",
                    "category": ev.category or "festival",
                }
            )

    day_events: dict[int, list[dict]] = {}
    if trip is not None:
        for stop in trip.stops:
            tokens = [t for t in re.split(r"[^a-z]+", (stop.name or "").lower()) if len(t) >= 4]
            stop_events = [e for e in events if any(t in (e.city or "").lower() for t in tokens)]
            for day in stop.days:
                hits = []
                for e in stop_events:
                    start, end = e.start_date, e.end_date or e.start_date
                    if start and end and start <= day.date <= end:
                        hits.append({"name": e.name, "category": e.category, "url": e.url})
                if hits:
                    day_events[day.id] = hits

    hotels_by_stop: dict[int, dict] = {}
    if trip is not None:
        for stop in trip.stops:
            hotel = stop.hotel
            if hotel is None:
                continue
            tags = hotel.tags or {}
            latlng = coords.get(hotel.id)
            hotels_by_stop[stop.id] = {
                "name": hotel.name,
                "area": hotel.area,
                "rating": hotel.rating,
                "price_per_night_nis": tags.get("price_per_night_nis"),
                "total_nis": tags.get("total_nis"),
                "why": tags.get("why"),
                "url": tags.get("website"),
                "lat": latlng[0] if latlng else None,
                "lng": latlng[1] if latlng else None,
            }

    # Budget aggregation (ground spend + booked flights, each counted once) lives in one place.
    if trip is not None:
        budget, flights = build_budget(trip, TOTAL_BUDGET_NIS)
    else:
        budget, flights = {}, []

    return HTMLResponse(
        render_plan(
            trip,
            by_stop,
            markers,
            event_markers,
            day_events,
            all_events,
            hotels_by_stop,
            budget,
            flights,
        )
    )
