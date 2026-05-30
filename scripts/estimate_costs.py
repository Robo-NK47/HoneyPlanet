"""Price every itinerary item (budget expert) and roll up day / stop totals.

Writes ItineraryItem.est_cost for each item, then recomputes each Day.est_cost and
Day.cost_breakdown bottom-up: item costs grouped by kind + the stop hotel's nightly lodging.
This makes every level consistent (overall = sum of countries = sum of stops = sum of days =
sum of items + lodging).

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/estimate_costs.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.agents import estimate_item_costs
from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, Stop, Trip

KIND_TO_CAT = {
    ItemKind.meal: "food",
    ItemKind.transit: "transport",
    ItemKind.activity: "activities",
    ItemKind.lodging: "lodging",
    ItemKind.free: "other",
}
CATS = ("lodging", "food", "transport", "activities", "other")


def _log(msg: str) -> None:
    print(msg, flush=True)


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, int | float) else default


async def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in .env")

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
            raise SystemExit("No trip found; run scripts/seed_plan.py first")

        for stop in trip.stops:
            days = sorted(stop.days, key=lambda d: d.date)
            items = [it for d in days for it in sorted(d.items, key=lambda x: x.order_index)]
            if not items:
                continue
            country = "Japan" if stop.country == "jp" else "Thailand"
            lines = []
            for it in items:
                tm = it.start_time.strftime("%H:%M") if it.start_time else "--:--"
                lines.append(f"id={it.id} [{it.kind.value}] {tm} {it.title or ''}")
            _log(f"\n=== {stop.name} ({len(items)} items) ===")

            result = await estimate_item_costs(
                stop_name=stop.name, country=country, items_text="\n".join(lines)
            )
            costs: dict[int, int] = {}
            for row in result.get("items") or []:
                rid = row.get("id")
                if isinstance(rid, int):
                    costs[rid] = _int(row.get("cost_nis"))

            applied = 0
            for it in items:
                if it.id in costs:
                    it.est_cost = costs[it.id]
                    applied += 1

            per_night = 0
            if stop.hotel:
                per_night = _int((stop.hotel.tags or {}).get("price_per_night_nis"))
            for day in days:
                bd = dict.fromkeys(CATS, 0)
                for it in day.items:
                    cat = KIND_TO_CAT.get(it.kind, "other")
                    if cat == "lodging":
                        continue  # lodging items are 0; the hotel covers lodging
                    bd[cat] += it.est_cost or 0
                bd["lodging"] = per_night
                day.cost_breakdown = bd
                day.est_cost = sum(bd.values())

            stop_total = sum(d.est_cost or 0 for d in days)
            _log(f"  priced {applied}/{len(items)} items · stop ≈ ₪{stop_total}")
            await session.commit()

    _log("\nItem-level cost estimation complete.")


if __name__ == "__main__":
    asyncio.run(main())
