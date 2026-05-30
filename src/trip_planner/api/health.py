"""Health endpoints. /health needs no database; /health/db probes Postgres + PostGIS."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from trip_planner import __version__
from trip_planner.config import settings
from trip_planner.db import SessionDep

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "env": settings.app_env,
    }


@router.get("/health/db")
async def health_db(session: SessionDep) -> dict:
    try:
        await session.execute(text("SELECT 1"))
        result = await session.execute(
            text("SELECT extversion FROM pg_extension WHERE extname = 'postgis'")
        )
        row = result.first()
        return {
            "status": "ok",
            "database": "reachable",
            "postgis": row[0] if row else None,
        }
    except Exception as exc:  # noqa: BLE001 — surface any connection/setup error to the caller
        return {"status": "error", "database": "unreachable", "detail": str(exc)}
