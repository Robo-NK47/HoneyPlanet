"""Generate full day-by-day itineraries for every stop using Claude (Opus 4.8).

Clears prior itinerary items and writes fresh ones (with times, transit, booking notices),
linking items to known places where the name matches.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/plan_trip.py
"""

from __future__ import annotations

import asyncio
from datetime import datetime, time

import anthropic
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Place, Stop, Trip
from trip_planner.plan.planner import StopPlan, plan_stop


def _parse_time(value: str | None) -> time | None:
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


async def apply_stop_plan(
    session: AsyncSession,
    days_by_date: dict[str, Day],
    places_by_name: dict[str, int],
    plan: StopPlan,
) -> int:
    written = 0
    for pday in plan.days:
        day = days_by_date.get(pday.date)
        if day is None:
            continue
        if pday.title:
            day.title = pday.title[:255]
        if pday.summary:
            day.summary = pday.summary
        for old in list(day.items):
            await session.delete(old)
        await session.flush()
        for idx, item in enumerate(pday.items):
            place_id = None
            if item.place_name:
                place_id = places_by_name.get(item.place_name.strip().lower())
            try:
                kind = ItemKind(item.kind)
            except ValueError:
                kind = ItemKind.activity
            session.add(
                ItineraryItem(
                    day_id=day.id,
                    place_id=place_id,
                    kind=kind,
                    title=item.title[:512],
                    start_time=_parse_time(item.start_time),
                    end_time=_parse_time(item.end_time),
                    order_index=idx,
                    transit_mode=(item.transit_mode[:128] if item.transit_mode else None),
                    transit_duration_min=item.transit_minutes,
                    notes=item.notes,
                    booking_notice=item.booking_notice,
                )
            )
            written += 1
    return written


async def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in .env")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async with async_session_maker() as session:
        trip = (
            await session.execute(
                select(Trip)
                .options(selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items))
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        if trip is None:
            raise SystemExit("No trip found; run scripts/seed_plan.py first")

        places = (await session.execute(select(Place))).scalars().all()
        by_stop: dict[int, list[Place]] = {}
        for place in places:
            sid = (place.tags or {}).get("stop_id")
            if sid is not None:
                by_stop.setdefault(sid, []).append(place)

        for stop in trip.stops:
            stop_places = by_stop.get(stop.id, [])
            place_dicts = [
                {
                    "name": p.name,
                    "category": (p.tags or {}).get("category") or p.subtype or "place",
                    "rating": p.rating,
                }
                for p in stop_places
            ]
            places_by_name = {p.name.strip().lower(): p.id for p in stop_places}
            days_by_date = {d.date.isoformat(): d for d in stop.days}
            dates = sorted(days_by_date)
            country = "Japan" if stop.country == "jp" else "Thailand"
            print(f"Planning {stop.name} ({len(dates)} days, {len(place_dicts)} places)...")

            plan = await asyncio.to_thread(
                plan_stop,
                client,
                stop_name=stop.name,
                country=country,
                dates=dates,
                places=place_dicts,
                trip_notes=trip.notes or "",
            )
            written = await apply_stop_plan(session, days_by_date, places_by_name, plan)
            await session.commit()
            print(f"  -> {written} itinerary items")

    print("Planning complete.")


if __name__ == "__main__":
    asyncio.run(main())
