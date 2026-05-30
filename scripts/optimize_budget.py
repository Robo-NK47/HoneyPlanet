"""Optimize the plan under the ₪50,000 budget by trimming ONLY dining + local transport.

Per the traveler's choices: hotels, paid attractions, and already-booked flights stay as-is;
savings come from cheaper local transport and trimming dining splurges. A global trim factor is
derived so the whole trip lands at the budget, then the budget-optimization expert chooses the
concrete cheaper-transport / value-dining swaps per stop and adds luggage-forwarding (takkyubin)
cost. Day/stop totals are recomputed so every level rolls up consistently.

Usage:  python scripts/optimize_budget.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.agents import optimize_stop
from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Stop, Trip

BUDGET_NIS = 50_000
BAGGAGE_RESERVE = 1_500  # headroom kept for luggage-forwarding the experts will add
BAGGAGE_PREFIX = "🧳"
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


FLIGHT_HINTS = (
    "flight", "fly", "el al", "airline", "airways", "nonstop",
    "tlv", "nrt", "hnd", "kix", "itm", "bkk", "dmk",
    "narita", "haneda", "kansai", "suvarnabhumi",
)


def _looks_like_flight(it: ItineraryItem) -> bool:
    if it.kind != ItemKind.transit:
        return False
    blob = f"{it.title or ''} {it.transit_mode or ''}".lower()
    return any(k in blob for k in FLIGHT_HINTS)


def _cuttable(it: ItineraryItem, stop_id: int, booked_ids: set[int]) -> bool:
    """Levers = dining + local transport. Booked international flights & all else stay fixed."""
    if it.kind == ItemKind.meal:
        return True
    if it.kind == ItemKind.transit:
        return not (_looks_like_flight(it) and stop_id in booked_ids)
    return False


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

        stops = list(trip.stops)
        per_night_of = {
            s.id: _int((s.hotel.tags or {}).get("price_per_night_nis")) if s.hotel else 0
            for s in stops
        }
        # The 3 booked international legs sit on the country-entry stops + the final stop.
        final_id = stops[-1].id if stops else None
        booked_ids: set[int] = {final_id} if final_id is not None else set()
        for i, s in enumerate(stops):
            if i == 0 or s.country != stops[i - 1].country:
                booked_ids.add(s.id)

        # Global split: what's fixed (hotels/attractions/flights/other) vs cuttable (dining+local).
        fixed_total = 0
        cuttable_total = 0
        for stop in stops:
            for d in stop.days:
                fixed_total += per_night_of[stop.id]
                for it in d.items:
                    c = it.est_cost or 0
                    if _cuttable(it, stop.id, booked_ids):
                        cuttable_total += c
                    elif it.kind != ItemKind.lodging:
                        fixed_total += c
        factor = 1.0
        if cuttable_total:
            factor = (BUDGET_NIS - fixed_total - BAGGAGE_RESERVE) / cuttable_total
            factor = max(0.30, min(1.0, factor))
        _log(
            f"fixed ≈ ₪{fixed_total} · cuttable ≈ ₪{cuttable_total} · "
            f"trim dining+local transport to ~{round(factor * 100)}%"
        )

        spent = 0
        for idx, stop in enumerate(stops):
            days = sorted(stop.days, key=lambda d: d.date)
            items = [it for d in days for it in sorted(d.items, key=lambda x: x.order_index)]
            if not items:
                continue
            country = "Japan" if stop.country == "jp" else "Thailand"
            stop_cuttable = sum(
                it.est_cost or 0 for it in items if _cuttable(it, stop.id, booked_ids)
            )
            target = round(stop_cuttable * factor)
            lines = []
            for it in items:
                tm = it.start_time.strftime("%H:%M") if it.start_time else "--:--"
                booked = _looks_like_flight(it) and stop.id in booked_ids
                tag = "FLIGHT-booked" if booked else it.kind.value
                lines.append(f"id={it.id} [{tag}] {tm} {it.title or ''} (now ₪{it.est_cost})")
            _log(f"\n=== {stop.name} (dining+local ₪{stop_cuttable} -> ₪{target}) ===")

            result = await optimize_stop(
                stop_name=stop.name,
                country=country,
                items_text="\n".join(lines),
                cuttable_now=stop_cuttable,
                cuttable_target=target,
                is_first_stop=(idx == 0),
            )

            # apply expert costs ONLY to dining + local transport
            costs: dict[int, int] = {}
            for row in result.get("items") or []:
                rid = row.get("id")
                if isinstance(rid, int):
                    costs[rid] = _int(row.get("cost_nis"))
            for it in items:
                if _cuttable(it, stop.id, booked_ids) and it.id in costs:
                    it.est_cost = costs[it.id]

            # luggage-forwarding line item on the stop's first day
            baggage = _int(result.get("baggage_nis"))
            if baggage > 0 and days:
                first = days[0]
                existing = next(
                    (it for it in first.items if (it.title or "").startswith(BAGGAGE_PREFIX)), None
                )
                if existing:
                    existing.est_cost = baggage
                else:
                    max_order = await session.scalar(
                        select(func.max(ItineraryItem.order_index)).where(
                            ItineraryItem.day_id == first.id
                        )
                    )
                    first.items.append(
                        ItineraryItem(
                            kind=ItemKind.transit,
                            title=f"{BAGGAGE_PREFIX} Luggage forwarding (takkyubin)",
                            order_index=(max_order or 0) + 1,
                            est_cost=baggage,
                            notes="Forward bags ahead so you travel light between hotels.",
                        )
                    )
                    await session.flush()

            # recompute day + stop from items + nightly lodging
            per_night = per_night_of[stop.id]
            stop_total = 0
            for day in days:
                bd = dict.fromkeys(CATS, 0)
                for it in day.items:
                    cat = KIND_TO_CAT.get(it.kind, "other")
                    if cat == "lodging":
                        continue
                    bd[cat] += it.est_cost or 0
                bd["lodging"] = per_night
                day.cost_breakdown = bd
                day.est_cost = sum(bd.values())
                stop_total += day.est_cost
            spent += stop_total
            cuts = "; ".join(result.get("cuts") or [])[:200]
            _log(f"  -> stop ≈ ₪{stop_total} · {cuts}")
            await session.commit()

        _log(f"\nOptimized trip total ≈ ₪{spent} / ₪{BUDGET_NIS}")
    _log("Optimization complete.")


if __name__ == "__main__":
    asyncio.run(main())
