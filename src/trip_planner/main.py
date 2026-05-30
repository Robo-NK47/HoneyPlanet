"""FastAPI application entry point.

Run locally:
    uvicorn trip_planner.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trip_planner import __version__
from trip_planner.api import health, places, plan
from trip_planner.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # Phase 0: intentionally no startup DB connection, so the API boots even before
    # Postgres is available. Probe connectivity on demand via GET /health/db.
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router)
    app.include_router(places.router)
    app.include_router(plan.router)

    @app.get("/", tags=["meta"])
    async def root() -> dict:
        return {
            "app": settings.app_name,
            "version": __version__,
            "docs": "/docs",
            "plan": "/plan",
        }

    return app


app = create_app()
