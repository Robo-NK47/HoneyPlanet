"""Create the PostGIS extension and all tables for local development.

Usage (repo root, venv active, deps installed, Postgres running):
    python scripts/init_db.py

This is a quick local bootstrap and produces the same tables as the Alembic migrations.
For anything beyond local dev, prefer:  alembic upgrade head
"""

from __future__ import annotations

import asyncio

from sqlalchemy import text

from trip_planner import models  # noqa: F401 — registers tables on Base.metadata
from trip_planner.db import Base, engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("Database initialized: PostGIS enabled, tables created.")


if __name__ == "__main__":
    asyncio.run(main())
