"""Recompute day/stop totals as ON-THE-GROUND spend, excluding the international flights.

The 3 booked international flights (transit_mode = 'international-flight') are reported in their
own Flights section, so they must not inflate per-day costs. This is the final costing step:
day.est_cost = on-the-ground items (by kind) + nightly lodging; flights are summed separately.

Usage:  python scripts/finalize_costs.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, Stop, Trip

INTL = "international-flight"
KIND_TO_CAT = {
    ItemKind.meal: "food",
    ItemKind.transit: "transport",
    ItemKind.activity: "activities",
    ItemKind.lodging: "lodging",
    ItemKind.free: "other",
}
CATS = ("lodging", "food", "transport", "activities", "other")


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, int | float) else default


async def main() -> None:
    async with async_session_maker() as session:
        trip = (
            await session.execute(
                select(Trip)
                .options(
                    selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items),
                    selectinload(Trip.stops).selectinload(Stop.hotel),
                )
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        if trip is None:
            raise SystemExit("No trip found")

        ground = 0
        flights = 0
        by_country: dict[str, int] = {}
        for stop in trip.stops:
            per_night = 0
            if stop.hotel:
                per_night = _int((stop.hotel.tags or {}).get("price_per_night_nis"))
            for day in stop.days:
                bd = dict.fromkeys(CATS, 0)
                for it in day.items:
                    if it.transit_mode == INTL:
                        flights += it.est_cost or 0
                        continue
                    cat = KIND_TO_CAT.get(it.kind, "other")
                    if cat == "lodging":
                        continue
                    bd[cat] += it.est_cost or 0
                bd["lodging"] = per_night
                day.cost_breakdown = bd
                day.est_cost = sum(bd.values())
                ground += day.est_cost
                code = stop.country or "?"
                by_country[code] = by_country.get(code, 0) + day.est_cost
        await session.commit()
        print(f"on-the-ground ≈ ₪{ground} · flights ≈ ₪{flights} · total ≈ ₪{ground + flights}")
        print("on-the-ground by country:", by_country)


if __name__ == "__main__":
    asyncio.run(main())
