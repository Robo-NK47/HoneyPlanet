"""Database engine, session factory, and declarative base.

The async engine is created at import time but does NOT connect until first use,
so the app boots even when Postgres is down. Use GET /health/db to probe it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from trip_planner.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _async_engine_config(raw_url: str) -> tuple[URL, dict]:
    """Normalize any standard Postgres URL for asyncpg.

    Forces the async driver (``postgresql://`` -> ``postgresql+asyncpg://``) and translates
    libpq's ``sslmode`` (which asyncpg rejects) into an asyncpg ``ssl`` connect arg, so a
    copy-pasted managed-provider URL (Neon, Supabase, …) works without hand-editing.
    """
    url = make_url(raw_url)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername="postgresql+asyncpg")
    query = dict(url.query)
    sslmode = query.pop("sslmode", None)
    query.pop("channel_binding", None)  # libpq-only; asyncpg doesn't accept it
    url = url.set(query=query)
    connect_args: dict = {}
    if sslmode and sslmode != "disable":
        connect_args["ssl"] = "require"
    return url, connect_args


_url, _connect_args = _async_engine_config(settings.database_url)
engine = create_async_engine(
    _url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
    connect_args=_connect_args,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with async_session_maker() as session:
        yield session


# Reusable FastAPI dependency alias (modern Annotated style).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
