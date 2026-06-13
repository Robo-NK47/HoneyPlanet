"""Apply the traveler's REAL booked hotels + the final Thailand structure to the plan.

Source of truth: the booking CSV. This:
  - sets every stop's hotel to the booked one (name + booked price, recomputed nightly lodging),
  - restructures Thailand to match the bookings — Bangkok 3n, Chiang Mai, Khao Lak,
    Koh Naka Yai, Bangkok 2n — replacing the old Krabi / Koh-Samui plan,
  - recomputes all day/stop/country/total costs (on-the-ground + the 3 booked flights),
  - marks hotel-booking tasks done and drops stale Krabi/Samui leg tasks.

Japan + both Bangkok stays keep their daily itineraries (only the hotel changes). The three new
Thailand destinations (Chiang Mai, Khao Lak, Koh Naka Yai) get fresh empty days — re-plan them
next. Atomic: everything commits at the end, or nothing does. A guard aborts if the DB is not in
the expected pre-state (so a second run can't corrupt it).

Usage:  python scripts/apply_booked_hotels.py
"""

from __future__ import annotations

import asyncio
from datetime import date as D
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.db import async_session_maker
from trip_planner.models import (
    Day,
    Event,
    ItemKind,
    ItineraryItem,
    Place,
    PlaceType,
    Stop,
    Task,
    Trip,
)

INTL = "international-flight"
KIND_TO_CAT = {
    ItemKind.meal: "food",
    ItemKind.transit: "transport",
    ItemKind.activity: "activities",
    ItemKind.lodging: "lodging",
    ItemKind.free: "other",
}
CATS = ("lodging", "food", "transport", "activities", "other")

# (name, country, nights, checkin, hotel, total_nis) in itinerary order.
JAPAN = [
    ("Tokyo", "jp", 4, D(2026, 11, 10), "lyf Shibuya Tokyo", 3013),
    ("Hakone", "jp", 2, D(2026, 11, 14), "Hotel Marroad Hakone", 2822),
    ("Kawaguchiko", "jp", 2, D(2026, 11, 16), "Maruei", 2362),
    ("Takayama", "jp", 2, D(2026, 11, 18), "hotel around TAKAYAMA", 711),
    ("Kanazawa", "jp", 2, D(2026, 11, 20), "Hotel Forza Kanazawa", 1382),
    ("Kyoto", "jp", 6, D(2026, 11, 22), "HOTEL RINGS KYOTO", 4708),
    ("Hiroshima & Miyajima", "jp", 3, D(2026, 11, 28), "Mercure Tokyu Stay Hiroshima", 1325),
    ("Osaka", "jp", 6, D(2026, 12, 1), "Hotel Royal Classic Osaka", 3879),
    ("Tokyo (shopping)", "jp", 3, D(2026, 12, 7), "HOTEL GROOVE SHINJUKU", 2560),
]
THAI = [
    ("Bangkok", "th", 3, D(2026, 12, 10), "Daraya Boutique Hotel", 723),
    ("Chiang Mai", "th", 6, D(2026, 12, 13), "Shamrock Chiangmai Hotel", 2879),
    ("Khao Lak", "th", 4, D(2026, 12, 19), "Devasom Khao Lak", 4983),
    ("Koh Naka Yai", "th", 5, D(2026, 12, 23), "The Naka Island", 12190),
    ("Bangkok", "th", 2, D(2026, 12, 28), "Daraya Boutique Hotel", 528),
]
JP_AREA = {0: "Shibuya", 8: "Shinjuku"}


async def main() -> None:
    async with async_session_maker() as session:
        trip = (
            await session.execute(
                select(Trip)
                .options(
                    selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items),
                )
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        if trip is None:
            raise SystemExit("No trip found")
        stops = {s.order_index: s for s in trip.stops}

        # --- Guard: only run against the known pre-state. ---
        if len(trip.stops) != 13:
            raise SystemExit(f"Expected 13 stops, found {len(trip.stops)} — already run?")
        if "krabi" not in (stops[10].name or "").lower():
            raise SystemExit(f"Stop 10 is {stops[10].name!r}, expected Krabi — aborting.")
        if "samui" not in (stops[11].name or "").lower():
            raise SystemExit(f"Stop 11 is {stops[11].name!r}, expected Koh Samui — aborting.")

        async def set_hotel(stop: Stop, name: str, country: str, total: int, nights: int) -> None:
            ppn = int(round(total / nights))
            place = await session.get(Place, stop.hotel_place_id) if stop.hotel_place_id else None
            if place is None:
                place = Place(name=name, type=PlaceType.hotel, country=country)
                session.add(place)
                await session.flush()
                stop.hotel_place_id = place.id
            place.name = name
            place.type = PlaceType.hotel
            place.country = country
            place.city = stop.name  # overwrite stale city (e.g. old Krabi/Samui places)
            place.area = None  # booked hotel — exact neighborhood unknown; avoid a stale one
            # Different hotel than before — drop the stale map pin (re-geocode later).
            place.location = None
            place.tags = {
                "price_per_night_nis": ppn,
                "total_nis": total,
                "why": f"Booked ✓ — ₪{total:,} for {nights} night(s)",
            }

        # Tokyo arrival + Tokyo shopping were sharing ONE hotel record — split them so the
        # arrival stay gets its own place (the two are different booked hotels).
        if stops[0].hotel_place_id and stops[0].hotel_place_id == stops[8].hotel_place_id:
            stops[0].hotel_place_id = None

        # --- Japan: structure already matches the CSV; swap in the booked hotels. ---
        for i, (_n, country, nights, checkin, hotel, total) in enumerate(JAPAN):
            s = stops[i]
            s.arrival_date = checkin
            s.departure_date = checkin + timedelta(days=nights)  # checkout
            s.nights = nights
            if i in JP_AREA:
                s.area = JP_AREA[i]
            await set_hotel(s, hotel, country, total, nights)

        bkk1, krabi, samui, bkk2 = stops[9], stops[10], stops[11], stops[12]

        # Drop old Krabi/Samui places (their pins + top-picks belong to removed destinations).
        for p in (await session.execute(select(Place))).scalars().all():
            sid = (p.tags or {}).get("stop_id")
            if sid in (krabi.id, samui.id) and p.type != PlaceType.hotel:
                await session.delete(p)
        await session.flush()

        # 1) Bangkok (first): 4 -> 3 nights — drop the surplus day(s), keep the itinerary.
        nm, country, nights, checkin, hotel, total = THAI[0]
        for d in sorted(bkk1.days, key=lambda x: x.date)[nights:]:
            await session.delete(d)
        bkk1.arrival_date, bkk1.departure_date, bkk1.nights = (
            checkin, checkin + timedelta(days=nights), nights,
        )
        await set_hotel(bkk1, hotel, country, total, nights)

        # 2) Krabi -> Chiang Mai: rebuild days, clear the (now-wrong) itinerary.
        nm, country, nights, checkin, hotel, total = THAI[1]
        for d in list(krabi.days):
            await session.delete(d)
        await session.flush()
        krabi.name, krabi.area = nm, "Old City"
        krabi.arrival_date, krabi.departure_date, krabi.nights = (
            checkin, checkin + timedelta(days=nights), nights,
        )
        krabi.notes = "Northern Thailand — temples, night markets, mountains. (Re-plan pending.)"
        for k in range(nights):
            session.add(Day(trip_id=trip.id, stop_id=krabi.id, date=checkin + timedelta(days=k)))
        await set_hotel(krabi, hotel, country, total, nights)

        # 3) Koh Samui -> Khao Lak: rebuild days, clear the itinerary.
        nm, country, nights, checkin, hotel, total = THAI[2]
        for d in list(samui.days):
            await session.delete(d)
        await session.flush()
        samui.name, samui.area = nm, "Khao Lak Beach"
        samui.arrival_date, samui.departure_date, samui.nights = (
            checkin, checkin + timedelta(days=nights), nights,
        )
        samui.notes = "Andaman coast — beaches, Similan gateway. (Re-plan pending.)"
        for k in range(nights):
            session.add(Day(trip_id=trip.id, stop_id=samui.id, date=checkin + timedelta(days=k)))
        await set_hotel(samui, hotel, country, total, nights)

        # 4) Bangkok (last): renumber to 13 to make room; set the booked hotel.
        nm, country, nights, checkin, hotel, total = THAI[4]
        bkk2.order_index = 13
        bkk2.arrival_date, bkk2.departure_date, bkk2.nights = (
            checkin, checkin + timedelta(days=nights), nights,
        )
        await set_hotel(bkk2, hotel, country, total, nights)

        # 5) Koh Naka Yai: brand-new stop at order 12.
        nm, country, nights, checkin, hotel, total = THAI[3]
        koh = Stop(
            trip_id=trip.id, name=nm, country=country, area="Naka Yai Island",
            order_index=12, arrival_date=checkin, departure_date=checkin + timedelta(days=nights),
            nights=nights, notes="The Naka Island resort — beach & relaxation. (Re-plan pending.)",
        )
        session.add(koh)
        await session.flush()
        for k in range(nights):
            session.add(Day(trip_id=trip.id, stop_id=koh.id, date=checkin + timedelta(days=k)))
        await set_hotel(koh, hotel, country, total, nights)
        await session.flush()

        # Drop seasonal events for the removed destinations; fix the stale Samui departure flight
        # (the trip now ends Koh Naka Yai → Phuket → Bangkok).
        for ev in (await session.execute(select(Event))).scalars().all():
            blob = f"{ev.name or ''} {ev.city or ''}".lower()
            if any(w in blob for w in ("krabi", "railay", "samui")):
                await session.delete(ev)
        for it in (await session.execute(select(ItineraryItem))).scalars().all():
            if "samui" in (it.title or "").lower():
                it.title = "Flight: Phuket (HKT) → Bangkok (BKK)"
                it.notes = (
                    (it.notes or "") + " Boat transfer Koh Naka Yai → Phuket, then flight."
                ).strip()
        await session.flush()

        # --- Tasks: hotels are booked; drop stale Krabi/Samui leg tasks. ---
        done = dropped = 0
        for tk in (await session.execute(select(Task))).scalars().all():
            low = (tk.title or "").lower()
            if low.startswith("book hotel") or "ryokan" in low or "kadan" in low:
                if not tk.done:
                    tk.done = True
                    done += 1
            elif any(w in low for w in ("krabi", "railay", "samui")):
                await session.delete(tk)
                dropped += 1
        await session.flush()

        # --- Recompute every cost level (on-the-ground + flights), flight-excluded. ---
        trip2 = (
            await session.execute(
                select(Trip)
                .options(selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items))
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        ground = flights = 0
        by_country: dict[str, int] = {}
        ppn_by_stop: dict[int, int] = {}
        for stop in trip2.stops:
            ppn = 0
            if stop.hotel_place_id:
                hp = await session.get(Place, stop.hotel_place_id)
                ppn = int((hp.tags or {}).get("price_per_night_nis") or 0) if hp else 0
            ppn_by_stop[stop.id] = ppn
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
                bd["lodging"] = ppn
                day.cost_breakdown = bd
                day.est_cost = sum(bd.values())
                ground += day.est_cost
                code = stop.country or "?"
                by_country[code] = by_country.get(code, 0) + day.est_cost

        # --- Summary (before commit, while objects are live). ---
        print("Stops after update:")
        for stop in sorted(trip2.stops, key=lambda x: x.order_index):
            hp = await session.get(Place, stop.hotel_place_id) if stop.hotel_place_id else None
            nit = sum(len(d.items) for d in stop.days)
            dc = sum(d.est_cost or 0 for d in stop.days)
            print(
                f"  [{stop.order_index:>2}] {stop.country} {stop.name:<22} "
                f"{stop.arrival_date}..{stop.departure_date} n={stop.nights} days={len(stop.days)} "
                f"items={nit:<3} hotel={hp.name if hp else None!r} "
                f"ppn={ppn_by_stop[stop.id]} dcost={dc}"
            )
        print(f"\nGround ≈ ₪{ground} | Flights ≈ ₪{flights} | TOTAL ≈ ₪{ground + flights}")
        print("On-the-ground by country:", by_country)
        print(f"Tasks: {done} bookings done, {dropped} stale Krabi/Samui tasks dropped.")

        await session.commit()
        print("\nCommitted. Next: re-plan Chiang Mai, Khao Lak, Koh Naka Yai.")


if __name__ == "__main__":
    asyncio.run(main())
