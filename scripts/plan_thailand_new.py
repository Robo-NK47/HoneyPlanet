"""Plan + price the 3 new Thailand destinations created from the booking CSV.

Chiang Mai (6n), Khao Lak (4n), and Koh Naka Yai (5n) have booked hotels + dates but no daily
itinerary. This generates a food-first, well-paced plan for each (the planner uses its own
expertise — no curated places exist for these yet), prices every item, and recomputes all
day/stop/country/total costs (international flights excluded).

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/plan_thailand_new.py
"""

from __future__ import annotations

import asyncio

import anthropic
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from trip_planner.agents import estimate_item_costs
from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Place, Stop, Trip
from trip_planner.plan.planner import plan_stop
from trip_planner.plan.writer import apply_stop_plan

INTL = "international-flight"
KIND_TO_CAT = {
    ItemKind.meal: "food",
    ItemKind.transit: "transport",
    ItemKind.activity: "activities",
    ItemKind.lodging: "lodging",
    ItemKind.free: "other",
}
CATS = ("lodging", "food", "transport", "activities", "other")

ADVISORIES = {
    "Chiang Mai": (
        "Northern Thailand, arriving from Bangkok (domestic flight BKK→CNX ~1h20) on the first "
        "day. Food-first on northern Thai cuisine: khao soi (Khao Soi Khun Yai / Mae Sai), sai ua "
        "(northern sausage), nam prik noom, Cowboy Hat Lady khao kha moo. Old City temples — Wat "
        "Phra Singh, Wat Chedi Luang; Doi Suthep (Wat Phra That) for city views. Nimmanhaemin for "
        "cafes/boutiques. Markets: Sunday Walking Street (Ratchadamnoen), Saturday Walking Street "
        "(Wualai), Warorot Market, Chang Phueak night food market. Include a Thai cooking class "
        "and an ETHICAL elephant sanctuary (e.g. Elephant Nature Park). Optional Doi Inthanon day "
        "trip (highest peak, waterfalls). Hotel is in the Old City. Rich but relaxed pace."
    ),
    "Khao Lak": (
        "Andaman-coast beach stay, arriving from Chiang Mai (flight CNX→Phuket HKT ~2h, then ~1h "
        "drive north to Khao Lak). Relaxed beach pace. Headline: a Similan Islands speedboat day "
        "trip (world-class snorkeling/diving; mid-December is peak season — needs booking ahead). "
        "Also Khao Lak-Lam Ru National Park viewpoints, Bang Niang & Nang Thong beaches, the "
        "Tsunami Memorial (Police Boat 813), Bang Niang night market. Superb southern-Thai "
        "seafood — grilled fish, tom yum, massaman. Beachfront hotel (Devasom). Leave real "
        "downtime: one big activity (Similan) plus beach days."
    ),
    "Koh Naka Yai": (
        "Private-island luxury-resort honeymoon finale (The Naka Island, off Phuket's east "
        "coast), arriving from Khao Lak (drive to Phuket ~1.5h + resort speedboat from Ao Po "
        "Grand Marina ~15min). Includes Christmas (Dec 25). Mostly relaxation: villa, private "
        "beach, spa, resort dining, sunsets. Add one or two boat excursions — Phang Nga Bay / "
        "James Bond Island with sea-kayaking among the limestone karsts, and a snorkeling trip "
        "around nearby islands. Optional half-day to Phuket Old Town (Sino-Portuguese streets, "
        "Sunday Walking Street, local food). Keep it indulgent and low-key — this is the splurge. "
        "The final day is departure: boat to Phuket, then the domestic flight to Bangkok. Flag "
        "resort-restaurant reservations and excursion bookings."
    ),
}


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

        targets = []
        for name in ADVISORIES:
            stop = next((s for s in trip.stops if s.name == name), None)
            if stop is None:
                raise SystemExit(f"Stop {name!r} not found — run apply_booked_hotels.py first")
            days_by_date = {d.date.isoformat(): d for d in stop.days}
            targets.append((stop, days_by_date, sorted(days_by_date)))

        # Plan only stops that have no items yet (idempotent — safe to re-run).
        to_plan = []
        for stop, days_by_date, dates in targets:
            count = (
                await session.execute(
                    select(func.count()).select_from(ItineraryItem).join(Day).where(
                        Day.stop_id == stop.id
                    )
                )
            ).scalar()
            if count:
                print(f"  {stop.name}: {count} items already planned — skipping", flush=True)
            else:
                to_plan.append((stop, days_by_date, dates))

        if to_plan:
            print("Planning " + ", ".join(s.name for s, _d, _x in to_plan) + "…", flush=True)
            plans = await asyncio.gather(
                *[
                    asyncio.to_thread(
                        plan_stop,
                        client,
                        stop_name=stop.name,
                        country="Thailand",
                        dates=dates,
                        places=[],
                        trip_notes=trip.notes or "",
                        advisories=ADVISORIES[stop.name],
                    )
                    for stop, _dbd, dates in to_plan
                ]
            )
            for (stop, days_by_date, _dates), plan in zip(to_plan, plans, strict=True):
                written = await apply_stop_plan(session, days_by_date, {}, plan)
                print(f"  {stop.name}: {written} items planned", flush=True)
            await session.commit()

        # Price every target — query items DIRECTLY (the Day.items relationship can be a stale
        # empty collection right after planning, since the session keeps objects on commit).
        priced = []
        for stop, _dbd, _dates in targets:
            items = (
                await session.execute(
                    select(ItineraryItem)
                    .join(Day)
                    .where(Day.stop_id == stop.id)
                    .order_by(Day.date, ItineraryItem.order_index)
                )
            ).scalars().all()
            lines = [
                f"id={it.id} [{it.kind.value}] "
                f"{it.start_time.strftime('%H:%M') if it.start_time else '--:--'} {it.title or ''}"
                for it in items
            ]
            priced.append((stop, items, "\n".join(lines)))

        results = await asyncio.gather(
            *[
                estimate_item_costs(stop_name=stop.name, country="Thailand", items_text=text)
                for stop, _items, text in priced
            ]
        )
        for (stop, items, _text), result in zip(priced, results, strict=True):
            costs: dict[int, int] = {}
            for row in result.get("items") or []:
                rid, val = row.get("id"), row.get("cost_nis")
                if isinstance(rid, int):
                    costs[rid] = int(val) if isinstance(val, int | float) else 0
            applied = sum(1 for it in items if it.id in costs)
            for it in items:
                if it.id in costs:
                    it.est_cost = costs[it.id]
            print(f"  {stop.name}: priced {applied}/{len(items)} items", flush=True)
        await session.commit()

        # Recompute every cost level (on-the-ground + flights), flight-excluded.
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
        for stop in trip2.stops:
            ppn = 0
            if stop.hotel_place_id:
                hp = await session.get(Place, stop.hotel_place_id)
                ppn = int((hp.tags or {}).get("price_per_night_nis") or 0) if hp else 0
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
        await session.commit()
        print(f"\nGround ≈ ₪{ground} | Flights ≈ ₪{flights} | TOTAL ≈ ₪{ground + flights}")
        print("On-the-ground by country:", by_country)


if __name__ == "__main__":
    asyncio.run(main())
