"""Apply the traveler's exact booked flight fares (2 pax) and add the missing flight home.

Run AFTER optimize_budget.py. Updates the inbound Japan and Japan->Thailand flight items to the
real fares, adds the Bangkok->Tel Aviv flight home (which was never costed), then recomputes every
day/stop total so the budget reflects the true flight cost.

Usage:  python scripts/apply_flight_fares.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Stop, Trip

FARE_TLV_JP = 4126  # Israel -> Japan
FARE_JP_TH = 1119  # Japan -> Thailand
FARE_TH_TLV = 3880  # Thailand -> Israel (flight home)

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


def _items(stop: Stop) -> list[ItineraryItem]:
    return [it for d in sorted(stop.days, key=lambda x: x.date) for it in d.items]


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
        stops = list(trip.stops)

        # 1. inbound to Japan (first stop) — El Al TLV -> NRT
        for it in _items(stops[0]):
            t = (it.title or "").lower()
            if it.kind == ItemKind.transit and "tlv" in t and ("nrt" in t or "el al" in t):
                it.est_cost = FARE_TLV_JP
                it.notes = f"✈️ Booked fare ₪{FARE_TLV_JP:,} (2 pax). {it.notes or ''}".strip()
                print(f"inbound Japan: {it.title} -> ₪{FARE_TLV_JP}")
                break

        # 2. Japan -> Thailand (first Thailand stop) — KIX -> BKK
        th_entry = next(
            (
                s
                for i, s in enumerate(stops)
                if s.country == "th" and (i == 0 or stops[i - 1].country != "th")
            ),
            None,
        )
        if th_entry:
            for it in _items(th_entry):
                t = (it.title or "").lower()
                if it.kind == ItemKind.transit and "kix" in t and "bkk" in t:
                    it.est_cost = FARE_JP_TH
                    it.notes = f"✈️ Booked fare ₪{FARE_JP_TH:,} (2 pax). {it.notes or ''}".strip()
                    print(f"Japan->Thailand: {it.title} -> ₪{FARE_JP_TH}")
                    break

        # 3. flight home (final stop, last day) — add if it isn't already an item
        final = stops[-1]
        last_day = sorted(final.days, key=lambda d: d.date)[-1]
        home = next(
            (
                it
                for it in last_day.items
                if "tlv" in (it.title or "").lower() or "tel aviv" in (it.title or "").lower()
            ),
            None,
        )
        if home is None:
            max_order = await session.scalar(
                select(func.max(ItineraryItem.order_index)).where(
                    ItineraryItem.day_id == last_day.id
                )
            )
            last_day.items.append(
                ItineraryItem(
                    kind=ItemKind.transit,
                    title="✈️ Flight home: Bangkok (BKK) → Tel Aviv (TLV)",
                    order_index=(max_order or 0) + 1,
                    est_cost=FARE_TH_TLV,
                    notes=f"✈️ Booked fare ₪{FARE_TH_TLV:,} (2 pax).",
                )
            )
            await session.flush()
            print(f"added flight home -> ₪{FARE_TH_TLV}")
        else:
            home.est_cost = FARE_TH_TLV
            print(f"flight home updated -> ₪{FARE_TH_TLV}")

        # recompute all day/stop totals
        total = 0
        by_country: dict[str, int] = {}
        for stop in stops:
            per_night = 0
            if stop.hotel:
                per_night = _int((stop.hotel.tags or {}).get("price_per_night_nis"))
            for day in stop.days:
                bd = dict.fromkeys(CATS, 0)
                for it in day.items:
                    cat = KIND_TO_CAT.get(it.kind, "other")
                    if cat == "lodging":
                        continue
                    bd[cat] += it.est_cost or 0
                bd["lodging"] = per_night
                day.cost_breakdown = bd
                day.est_cost = sum(bd.values())
                total += day.est_cost
                code = stop.country or "?"
                by_country[code] = by_country.get(code, 0) + day.est_cost
        await session.commit()
        print(f"\nNEW TOTAL ≈ ₪{total} / ₪50000")
        print("by country:", by_country)


if __name__ == "__main__":
    asyncio.run(main())
