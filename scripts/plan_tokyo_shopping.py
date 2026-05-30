"""Plan and price the new 'Tokyo (shopping)' stop (the final 3 Japan days).

Generates a shopping-focused but still food-first 3-day Tokyo itinerary, links known places, and
prices each item. Run AFTER restructure_japan.py and BEFORE finalize_costs.py.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/plan_tokyo_shopping.py
"""

from __future__ import annotations

import asyncio

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.agents import estimate_item_costs
from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, Place, Stop, Trip
from trip_planner.plan.planner import plan_stop
from trip_planner.plan.writer import apply_stop_plan

ADVISORY = (
    "FINAL 3 DAYS IN TOKYO — make these shopping-focused: Ginza (department stores, Uniqlo/Muji "
    "flagships), Shinjuku, Shibuya (Shibuya 109, Parco, Don Quijote), Harajuku/Omotesando, "
    "Akihabara (electronics/anime), Asakusa Nakamise, and depachika food halls for edible gifts. "
    "Keep it food-first with superb Tokyo meals. The couple arrives from Osaka by Shinkansen on "
    "the first of these days; on the final day they fly Tokyo (HND) → Bangkok — keep that day "
    "light. Flag anything needing reservations."
)


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
            raise SystemExit("No trip found")
        shop = next((s for s in trip.stops if s.name == "Tokyo (shopping)"), None)
        if shop is None:
            raise SystemExit("'Tokyo (shopping)' not found — run restructure_japan.py first")

        places = (await session.execute(select(Place))).scalars().all()
        tokyo = next((s for s in trip.stops if s.name == "Tokyo"), None)
        tokyo_id = tokyo.id if tokyo else None
        tokyo_places = [p for p in places if (p.tags or {}).get("stop_id") == tokyo_id]
        place_dicts = [
            {
                "name": p.name,
                "category": (p.tags or {}).get("category") or p.subtype or "place",
                "rating": p.rating,
            }
            for p in tokyo_places
        ]
        places_by_name = {p.name.strip().lower(): p.id for p in tokyo_places}
        days_by_date = {d.date.isoformat(): d for d in shop.days}
        dates = sorted(days_by_date)
        print(f"Planning Tokyo (shopping): {dates}", flush=True)

        plan = await asyncio.to_thread(
            plan_stop,
            client,
            stop_name="Tokyo (shopping)",
            country="Japan",
            dates=dates,
            places=place_dicts,
            trip_notes=trip.notes or "",
            advisories=ADVISORY,
        )
        written = await apply_stop_plan(session, days_by_date, places_by_name, plan)
        await session.commit()
        print(f"  {written} items", flush=True)

        # re-read fresh items and price them
        fresh = (
            await session.execute(
                select(Day)
                .where(Day.stop_id == shop.id)
                .options(selectinload(Day.items))
                .order_by(Day.date)
            )
        ).scalars().all()
        items = [it for d in fresh for it in sorted(d.items, key=lambda x: x.order_index)]
        lines = []
        for it in items:
            tm = it.start_time.strftime("%H:%M") if it.start_time else "--:--"
            lines.append(f"id={it.id} [{it.kind.value}] {tm} {it.title or ''}")
        result = await estimate_item_costs(
            stop_name="Tokyo (shopping)", country="Japan", items_text="\n".join(lines)
        )
        costs: dict[int, int] = {}
        for row in result.get("items") or []:
            rid = row.get("id")
            val = row.get("cost_nis")
            if isinstance(rid, int):
                costs[rid] = int(val) if isinstance(val, int | float) else 0
        applied = 0
        for it in items:
            if it.id in costs:
                it.est_cost = costs[it.id]
                applied += 1
        await session.commit()
        print(f"  priced {applied}/{len(items)} items", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
