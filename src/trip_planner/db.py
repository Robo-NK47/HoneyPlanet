"""Database engine, session factory, and declarative base.

The async engine is created at import time but does NOT connect until first use,
so the app boots even when Postgres is down. Use GET /health/db to probe it.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from trip_planner.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields a database session."""
    async with async_session_maker() as session:
        yield session


# Reusable FastAPI dependency alias (modern Annotated style).
SessionDep = Annotated[AsyncSession, Depends(get_session)]
