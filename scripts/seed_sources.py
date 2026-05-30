"""Insert the seed sources into the database.

Usage (DB connected):  python scripts/seed_sources.py
"""

from __future__ import annotations

import asyncio

from trip_planner.db import async_session_maker
from trip_planner.ingest.sources import upsert_sources


async def main() -> None:
    async with async_session_maker() as session:
        added = await upsert_sources(session)
        await session.commit()
    print(f"Seed sources upserted. Newly added: {added}")


if __name__ == "__main__":
    asyncio.run(main())
