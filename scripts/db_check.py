"""Quick database connectivity + schema check.

Usage (DB connected):  python scripts/db_check.py
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from trip_planner.db import engine


async def main() -> None:
    async with engine.connect() as conn:
        postgis = (
            await conn.execute(
                text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
            )
        ).scalar()
        result = await conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' ORDER BY table_name"
            )
        )
        tables = result.scalars().all()
    await engine.dispose()
    print(f"PostGIS extension: {postgis}")
    print(f"Tables ({len(tables)}): {', '.join(tables)}")


if __name__ == "__main__":
    asyncio.run(main())
