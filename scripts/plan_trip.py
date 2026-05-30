"""Generate full day-by-day itineraries for every stop using Claude (Opus 4.8).

Clears prior itinerary items and writes fresh ones (times, transit, booking notices),
linking items to known places where the name matches.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/plan_trip.py
"""

from __future__ import annotations

import asyncio

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, Place, Stop, Trip
from trip_planner.plan.planner import plan_stop
from trip_planner.plan.writer import apply_stop_plan


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
