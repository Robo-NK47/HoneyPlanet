"""Restructure the Japan leg per the traveler's request.

  - Tokyo arrival trimmed to 4 days (keeps its first 4 planned days).
  - Middle stops (Hakone..Osaka) keep their nights but shift 3 days earlier.
  - A new 3-day "Tokyo (shopping)" stop is added at the end (Dec 7-9).
  - The Japan->Thailand flight now departs Tokyo; exact booked fares applied.
  - The 3 international flights are marked (transit_mode sentinel) so they can live in their
    own Flights section instead of inside the daily plan.

Run AFTER optimize_budget.py. Re-plan the new shopping days and re-price afterwards.

Usage:  python scripts/restructure_japan.py
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Stop, Trip

INTL = "international-flight"  # transit_mode sentinel -> rendered in the Flights section
FARE_TLV_JP = 4126
FARE_JP_TH = 1119
FARE_TH_TLV = 3880
TOKYO_ARRIVAL_DAYS = 4
SHIFT = 3


def _items(stop: Stop) -> list[ItineraryItem]:
    return [it for d in sorted(stop.days, key=lambda x: x.date) for it in d.items]


async def main() -> None:
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
        stops = list(trip.stops)
        jp = [s for s in stops if s.country == "jp"]
        th = [s for s in stops if s.country == "th"]
        tokyo, osaka = jp[0], jp[-1]
        bkk_first, bkk_last = th[0], th[-1]

        # 1. Trim Tokyo arrival to 4 days (delete the surplus days + their items)
        tdays = sorted(tokyo.days, key=lambda d: d.date)
        for d in tdays[TOKYO_ARRIVAL_DAYS:]:
            await session.delete(d)
        await session.flush()
        tokyo.nights = TOKYO_ARRIVAL_DAYS
        tokyo.departure_date = tdays[TOKYO_ARRIVAL_DAYS - 1].date

        # 2. Shift middle stops 3 days earlier (content/costs travel with them)
        for s in jp[1:]:
            for d in s.days:
                d.date = d.date - timedelta(days=SHIFT)
            if s.arrival_date:
                s.arrival_date -= timedelta(days=SHIFT)
            if s.departure_date:
                s.departure_date -= timedelta(days=SHIFT)
        await session.flush()

        # 3. New Tokyo shopping stop after Osaka; make room in the ordering for it
        for s in th:
            s.order_index += 1
        osaka_last = max(d.date for d in osaka.days)
        shop_arr = osaka_last + timedelta(days=1)
        shop = Stop(
            trip_id=trip.id,
            name="Tokyo (shopping)",
            country="jp",
            area="Ginza / Shinjuku / Shibuya",
            order_index=osaka.order_index + 1,
            arrival_date=shop_arr,
            departure_date=shop_arr + timedelta(days=TOKYO_ARRIVAL_DAYS - 2),
            nights=3,
            notes="Final 3 days in Tokyo — shopping-focused, then fly to Bangkok.",
        )
        session.add(shop)
        await session.flush()
        shop.hotel_place_id = tokyo.hotel_place_id  # reuse the Tokyo hotel for the shopping stay
        for i in range(3):
            session.add(Day(trip_id=trip.id, stop_id=shop.id, date=shop_arr + timedelta(days=i)))
        await session.flush()

        # 4. Flights — mark internationals, set exact fares, fix routing
        for it in _items(tokyo):
            t = (it.title or "").lower()
            if it.kind == ItemKind.transit and ("el al" in t or "tlv" in t):
                it.transit_mode = INTL
                it.est_cost = FARE_TLV_JP
                it.notes = f"✈️ Booked fare ₪{FARE_TLV_JP:,} (2 pax). {it.notes or ''}".strip()

        for it in _items(bkk_first):
            t = (it.title or "").lower()
            if it.kind == ItemKind.transit and "bkk" in t and ("kix" in t or "flight" in t):
                it.title = "✈️ Tokyo (HND) → Bangkok (BKK) + transfer to hotel"
                it.transit_mode = INTL
                it.est_cost = FARE_JP_TH
                it.notes = f"✈️ Booked fare ₪{FARE_JP_TH:,} (2 pax). {it.notes or ''}".strip()
                break

        for d in osaka.days:
            for it in list(d.items):
                t = (it.title or "").lower()
                if "kix" in t and ("depart" in t or "prep" in t):
                    await session.delete(it)

        last_day = sorted(bkk_last.days, key=lambda d: d.date)[-1]
        if not any("tlv" in (it.title or "").lower() for it in last_day.items):
            mo = await session.scalar(
                select(func.max(ItineraryItem.order_index)).where(
                    ItineraryItem.day_id == last_day.id
                )
            )
            last_day.items.append(
                ItineraryItem(
                    kind=ItemKind.transit,
                    transit_mode=INTL,
                    title="✈️ Flight home: Bangkok (BKK) → Tel Aviv (TLV)",
                    order_index=(mo or 0) + 1,
                    est_cost=FARE_TH_TLV,
                    notes=f"✈️ Booked fare ₪{FARE_TH_TLV:,} (2 pax). Departs Dec 30.",
                )
            )
        await session.commit()
        print(
            f"Done. Tokyo arrival {tokyo.arrival_date}..{tokyo.departure_date} | "
            f"shopping {shop.arrival_date}..{shop.departure_date} | "
            f"Osaka ends {osaka.departure_date}"
        )


if __name__ == "__main__":
    asyncio.run(main())
