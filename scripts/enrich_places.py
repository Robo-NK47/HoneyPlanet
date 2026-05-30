"""Fetch top places (restaurants/attractions/theme parks/food markets) per stop into the DB.

Uses the Google Places API. Usage (DB + key configured):  python scripts/enrich_places.py
"""

from __future__ import annotations

import asyncio

import httpx
from sqlalchemy import select

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.enrich.seed_places import enrich_stop_places
from trip_planner.models import Stop


async def main() -> None:
    if not settings.google_maps_api_key:
        raise SystemExit("GOOGLE_MAPS_API_KEY is not set in .env")

    async with async_session_maker() as session, httpx.AsyncClient() as client:
        stops = (await session.execute(select(Stop).order_by(Stop.order_index))).scalars().all()
        total = 0
        for stop in stops:
            added = await enrich_stop_places(session, client, settings.google_maps_api_key, stop)
            await session.commit()
            print(f"  {stop.name:24} +{added} places")
            total += added
    print(f"Done. Added {total} places.")


if __name__ == "__main__":
    asyncio.run(main())
