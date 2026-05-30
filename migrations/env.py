"""Alembic environment — async-aware, sharing the app's engine (so Neon/SSL URLs work).

Offline mode (`alembic upgrade head --sql`) renders DDL without a database, which is how we
validate migrations without a live Postgres.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

import geoalchemy2  # noqa: F401 — registers spatial types so they render in migrations
from alembic import context
from sqlalchemy.engine import Connection

import trip_planner.models  # noqa: F401 — imports all models onto Base.metadata
from trip_planner.db import Base, engine

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=engine.url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
