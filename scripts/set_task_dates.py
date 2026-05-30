"""Give every task a real 'last date to do it' (a book-by deadline).

Each booking task is mapped to the stop it concerns and dated by that stop's arrival minus a
lead time appropriate to the task type:
  - hotels / ryokan (Japan): 70 days   (peak autumn — book early or they sell out)
  - hotels (Thailand):       45 days
  - flights:                 45 days
  - trains / buses / boats:  30 days    (JR reservations open ~1 month out)
  - dining reservations:     30 days
  - budget / planning:       trip start - 90 days (decide before booking season)

Usage:  python scripts/set_task_dates.py
"""

from __future__ import annotations

import asyncio
import re
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.db import async_session_maker
from trip_planner.models import Stop, Task, Trip


async def main() -> None:
    async with async_session_maker() as session:
        trip = (
            await session.execute(
                select(Trip)
                .options(selectinload(Trip.stops).selectinload(Stop.hotel))
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        if trip is None:
            raise SystemExit("No trip found")

        stops = [s for s in trip.stops if s.arrival_date]
        hotel_to_stop: dict[str, Stop] = {}  # a shared hotel -> its earliest stay
        for s in stops:
            if s.hotel and s.hotel.name:
                key = s.hotel.name.lower()
                if key not in hotel_to_stop or s.arrival_date < hotel_to_stop[key].arrival_date:
                    hotel_to_stop[key] = s
        city_to_stops: dict[str, list[Stop]] = {}
        for s in stops:
            city_to_stops.setdefault((s.name or "").lower(), []).append(s)
        for v in city_to_stops.values():
            v.sort(key=lambda x: x.arrival_date)

        used: dict[str, int] = {}

        def first_for_city(city: str) -> Stop | None:
            key = city.lower().strip()
            lst = city_to_stops.get(key)
            if not lst:
                for k, v in city_to_stops.items():
                    if key and (key in k or k in key):
                        lst = v
                        break
            return lst[0] if lst else None

        def indexed_for_city(city: str) -> Stop | None:
            key = city.lower().strip()
            lst = city_to_stops.get(key)
            if not lst:
                for k, v in city_to_stops.items():
                    if key and (key in k or k in key):
                        lst = v
                        break
            if not lst:
                return None
            i = used.get(key, 0)
            used[key] = i + 1
            return lst[min(i, len(lst) - 1)]

        budget_deadline = trip.start_date - timedelta(days=90)
        tasks = (await session.execute(select(Task))).scalars().all()
        rows = []
        for t in sorted(tasks, key=lambda x: x.id):
            title = t.title or ""
            low = title.lower()
            due = None
            if low.startswith("book hotel:"):
                stop = next((s for h, s in hotel_to_stop.items() if h in low), None)
                if stop is None:
                    m = re.search(r"\(([^()]+)\)\s*$", title)
                    stop = first_for_city(m.group(1)) if m else None
                if stop:
                    lead = 70 if stop.country == "jp" else 45
                    due = stop.arrival_date - timedelta(days=lead)
            elif low.startswith("book transport:"):
                dest = title.rsplit("→", 1)[-1].strip() if "→" in title else ""
                stop = indexed_for_city(dest)
                if stop:
                    lead = 45 if "flight" in low else 30
                    due = stop.arrival_date - timedelta(days=lead)
            elif "kadan" in low or "ryokan" in low:
                stop = first_for_city("hakone")
                due = stop.arrival_date - timedelta(days=70) if stop else None
            elif "omakase" in low or low.startswith("reserve"):
                stop = first_for_city("tokyo")
                due = stop.arrival_date - timedelta(days=30) if stop else None
            if due is None:
                due = budget_deadline
            t.due_date = due
            rows.append((due.isoformat(), t.importance, title))
        await session.commit()

        for due, imp, title in sorted(rows):
            print(f"{due}  [{imp:<6}] {title[:72]}")
        print(f"\nDated {len(rows)} tasks. None left without a deadline.")


if __name__ == "__main__":
    asyncio.run(main())
