# Trip Planner 🗾🏝️

Offline-first honeymoon planner for **Japan (deep)** + **Thailand (light)**. It scrapes travel
blogs, categorizes places by **coordinates** and **type**, maintains a **knowledge graph**
([graphify](https://github.com/safishamsi/graphify)), and plans the trip at **meta** (where, when)
and **per-day** (what, where to eat, how to get around) levels. View the plan **offline** on a
phone (PWA); **edit** it online.

> **Status: Phase 0 (scaffold).** FastAPI + Postgres/PostGIS skeleton, schema, config, and
> API-key guides. See [docs/SPEC.md](docs/SPEC.md) for the full requirements and roadmap.

## Architecture (target)

| Layer | Choice |
| --- | --- |
| Backend API | Python + FastAPI |
| System of record | PostgreSQL + PostGIS |
| Knowledge graph | graphify over the scraped corpus → tags/edges in Postgres |
| Scraping | httpx + trafilatura (Hebrew-friendly), robots.txt-respecting |
| Extract & categorize | Claude (Anthropic) |
| Geocoding | Hybrid: Nominatim (free) → Google Places (fallback) |
| Frontend | PWA (React + Vite), offline view, online edit + sync, bilingual EN/HE |
| Hosting | Managed cloud (Fly.io + managed Postgres) |

## Quickstart (Windows / PowerShell)

```powershell
# 1. Start Postgres + PostGIS (requires Docker)
docker compose up -d db

# 2. Create a virtualenv and install (Python 3.11+)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3. Configure environment (defaults already match docker-compose)
Copy-Item .env.example .env

# 4. Create the schema (PostGIS extension + tables)
python scripts/init_db.py

# 5. Run the API
uvicorn trip_planner.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>, and check the DB wiring at
<http://127.0.0.1:8000/health/db>.

Run the smoke tests (no database needed):

```powershell
pytest
```

## Project layout

```
trip-planner/
├─ docker-compose.yml      # local Postgres + PostGIS
├─ pyproject.toml          # deps + tooling (extras: ingest/llm/geo/dev, added per phase)
├─ .env.example            # copy to .env
├─ docs/
│  ├─ SPEC.md              # requirements v1 + roadmap (source of truth)
│  ├─ setup-google-maps.md # how to get the Google Maps key (Phase 2)
│  └─ setup-anthropic.md   # how to get the Anthropic key (Phase 2)
├─ scripts/
│  └─ init_db.py           # create PostGIS extension + tables
├─ src/trip_planner/
│  ├─ main.py              # FastAPI app
│  ├─ config.py            # settings (.env)
│  ├─ db.py                # async engine + session
│  ├─ models.py            # Source, Place, PlaceMention, Trip, Stop, Day, ItineraryItem, EditLog
│  ├─ schemas.py           # Pydantic API models
│  └─ api/                 # health + places routers
└─ tests/                  # smoke tests
```

## Data model (Phase 0)

- **Source** → **PlaceMention** → **Place** — places with provenance (who mentioned them),
  PostGIS `POINT` coordinates, and a `type` (restaurant / activity / hotel / other).
- **Trip** → **Stop** (meta: city stays) → **Day** → **ItineraryItem** (meal/activity/transit…).
- **EditLog** — audit trail tagged by origin (laptop vs phone) for sync.

## What's next

- Provide the three open inputs in [docs/SPEC.md](docs/SPEC.md): **budget**, **flights**, **seed blogs**.
- **Phase 1 — Ingest:** source registry, scraper, raw cache, Alembic migrations.
