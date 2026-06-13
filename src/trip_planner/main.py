"""FastAPI application entry point.

Run locally (avoid --reload: its reloader runs workers under the system Python, not the venv):
    uvicorn trip_planner.main:app
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trip_planner import __version__
from trip_planner.api import auth, chat, health, places, plan, tasks
from trip_planner.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    # Phase 0: intentionally no startup DB connection, so the API boots even before
    # Postgres is available. Probe connectivity on demand via GET /health/db.
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan)

    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    allow_all = not origins or origins == ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if allow_all else origins,
        # '*' with credentials is invalid per the CORS spec — only allow credentials when the
        # caller has pinned explicit origins (needed for the cross-origin auth cookie).
        allow_credentials=not allow_all,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(health.router)
    app.include_router(places.router)
    app.include_router(plan.router)
    app.include_router(chat.router)
    app.include_router(tasks.router)

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
