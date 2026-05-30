"""Seed a first-draft honeymoon itinerary into the database (idempotent).

This is a hand-drafted starting point (no external APIs) so there's something to *view* while
Phase 2 enrichment and the real planner come together. Flights are assumed — see TRIP_NOTES.

Usage (DB connected):  python scripts/seed_plan.py
"""

from __future__ import annotations

import asyncio
from datetime import date, time, timedelta

from sqlalchemy import select

from trip_planner.db import async_session_maker
from trip_planner.models import Day, ItemKind, ItineraryItem, Stop, Trip

TRIP_NAME = "Honeymoon — Japan & Thailand"
START = date(2026, 11, 10)
END = date(2026, 12, 30)
TRIP_NOTES = (
    "Budget ~NIS 50,000 (excl. booked intl flights). Style: food-first, balanced, "
    "comfort + splurges. Flights ASSUMED — arrive Tokyo; KIX->BKK on Dec 10; home Dec 30. "
    "Confirm flights to anchor the plan."
)
TRAVELERS = {
    "p1": "Nadav (35)",
    "p2": "wife (32)",
    "style": "food-first, balanced, comfort+splurge",
}

# (name, country, region, nights, note)
JAPAN_STOPS = [
    ("Tokyo", "jp", "Kanto", 7, "Tsukiji, ramen, izakaya, omakase; teamLab; Shinjuku jazz"),
    ("Hakone", "jp", "Kanagawa", 2, "Splurge: Gora Kadan ryokan; onsen; Lake Ashi; Fuji"),
    ("Kawaguchiko", "jp", "Yamanashi", 2, "Fufu Kawaguchiko ryokan; Mt Fuji views"),
    ("Takayama", "jp", "Gifu", 2, "Old town, morning market, Hida beef, sake"),
    ("Kanazawa", "jp", "Ishikawa", 2, "Omicho seafood market, Kenrokuen garden"),
    ("Kyoto", "jp", "Kansai", 6, "Temples, Sagano train, Nishiki market, kaiseki"),
    ("Hiroshima & Miyajima", "jp", "Chugoku", 3, "Iwaso ryokan, okonomiyaki, Itsukushima"),
    ("Osaka", "jp", "Kansai", 6, "Dotonbori street food; Nara day trip; fly KIX->BKK"),
]
THAILAND_STOPS = [
    ("Bangkok", "th", "Central", 4, "Street food, Michelin, markets, temples"),
    ("Krabi / Railay", "th", "Andaman", 6, "Beaches, longtails, climbing, island hops"),
    ("Koh Samui", "th", "Gulf", 8, "Beach relaxation, spa, seafood"),
    ("Bangkok", "th", "Central", 2, "Final bites; fly home Dec 30"),
]

# date -> list of (kind, title, start_time, note) — a few illustrative days
SAMPLE_ITEMS: dict[date, list[tuple[str, str, time | None, str | None]]] = {
    date(2026, 11, 10): [
        ("activity", "Arrive Tokyo, check in, settle", time(15, 0), None),
        ("meal", "Dinner: izakaya at Omoide Yokocho", time(19, 0), "Yakitori + beer"),
    ],
    date(2026, 11, 11): [
        ("meal", "Breakfast: Tsukiji Outer Market", time(8, 0), "Tamago, sushi, uni"),
        ("activity", "teamLab Planets", time(11, 0), "Book timed tickets"),
        ("meal", "Ramen lunch", time(13, 30), None),
        ("activity", "Shinjuku jazz bar", time(20, 0), "Live set"),
    ],
    date(2026, 11, 17): [
        ("transit", "Odakyu Romancecar to Hakone", time(10, 0), None),
        ("activity", "Check in Gora Kadan; onsen", time(14, 0), "Splurge night"),
        ("meal", "Kaiseki dinner at the ryokan", time(18, 30), None),
    ],
}


async def main() -> None:
    async with async_session_maker() as session:
        # Idempotent: drop any prior draft with the same name (cascades to stops/days/items).
        for prior in (await session.execute(select(Trip).where(Trip.name == TRIP_NAME))).scalars():
            await session.delete(prior)
        await session.flush()

        # Build the whole object graph first, then add the root once so the cascade persists
        # stops/days/items in one shot (adding the Trip before its children skips the cascade).
        trip = Trip(
            name=TRIP_NAME, start_date=START, end_date=END, travelers=TRAVELERS, notes=TRIP_NOTES
        )

        cursor = START
        for order, (name, country, region, nights, note) in enumerate(JAPAN_STOPS + THAILAND_STOPS):
            arrival = cursor
            departure = cursor + timedelta(days=nights)
            stop = Stop(
                trip=trip,
                name=name,
                country=country,
                region=region,
                arrival_date=arrival,
                departure_date=departure,
                nights=nights,
                order_index=order,
                notes=note,
            )
            for i in range(nights):
                d = arrival + timedelta(days=i)
                day = Day(trip=trip, stop=stop, date=d, title=f"{name} — Day {i + 1}", summary=note)
                for j, (kind, title, start, inote) in enumerate(SAMPLE_ITEMS.get(d, [])):
                    ItineraryItem(
                        day=day, kind=ItemKind(kind), title=title, start_time=start,
                        order_index=j, notes=inote,
                    )
            cursor = departure

        session.add(trip)
        await session.commit()
    print(f"Draft plan seeded: '{TRIP_NAME}' ({START} -> {END}).")


if __name__ == "__main__":
    asyncio.run(main())
