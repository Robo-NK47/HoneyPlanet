# Trip Planner 🗾🏝️

Offline-first honeymoon planner for **Japan (deep)** + **Thailand (light)**. It scrapes travel
blogs, categorizes places by **coordinates** and **type**, maintains a **knowledge graph**
([graphify](https://github.com/safishamsi/graphify)), and plans the trip at **meta** (where, when)
and **per-day** (what, where to eat, how to get around) levels. View the plan **offline** on a
phone (PWA); **edit** it online.

> **Status: Phase 1 (ingestion).** FastAPI + Postgres/PostGIS, Alembic migrations, and a
> polite scraper → text-extractor → `Document` pipeline. See [docs/SPEC.md](docs/SPEC.md)
> for the full requirements and roadmap.

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
alembic upgrade head    # canonical; or `python scripts/init_db.py` for a quick local bootstrap

# 5. Run the API
uvicorn trip_planner.main:app --reload
```

Then open <http://127.0.0.1:8000/docs>, and check the DB wiring at
<http://127.0.0.1:8000/health/db>.

Run the tests (no database needed):

```powershell
pytest
```

## Ingestion (Phase 1)

With a database connected:

```powershell
alembic upgrade head            # apply schema
python scripts/seed_sources.py  # register starter sources
python scripts/ingest.py        # fetch + extract + store all sources
python scripts/ingest.py https://www.japan-guide.com/e/e2164.html   # …or specific URLs
```

The fetcher respects `robots.txt`, rate-limits per host, and caches raw HTML under `data/cache/`.
Extracted main text lands in the `document` table, ready for Phase-2 place extraction.

## Viewing the draft plan

A first-draft itinerary lives in the `Trip → Stop → Day → ItineraryItem` tables — seed it with
`python scripts/seed_plan.py`. With the server running (`uvicorn trip_planner.main:app`), open
<http://127.0.0.1:8000/plan> for a read-only view. The offline, editable phone app is Phase 5.

## Project layout

```
trip-planner/
├─ docker-compose.yml      # local Postgres + PostGIS
├─ alembic.ini             # migrations config (URL injected from settings)
├─ pyproject.toml          # deps + tooling (extras: ingest/llm/geo/dev, added per phase)
├─ .env.example            # copy to .env
├─ docs/                   # SPEC.md (source of truth) + API-key setup guides
├─ migrations/             # Alembic (env.py + versions/0001_initial.py)
├─ scripts/
│  ├─ init_db.py           # quick local bootstrap (create_all)
│  ├─ seed_sources.py      # register seed sources
│  └─ ingest.py            # fetch + extract + store documents
├─ src/trip_planner/
│  ├─ main.py              # FastAPI app
│  ├─ config.py            # settings (.env)
│  ├─ db.py                # async engine + session
│  ├─ models.py            # Source/Place/PlaceMention, Trip/Stop/Day/ItineraryItem, Document, EditLog
│  ├─ schemas.py           # Pydantic API models
│  ├─ api/                 # health + places routers
│  └─ ingest/              # robots, fetcher, extract, sources, pipeline
└─ tests/                  # unit + smoke tests
```

## Data model (Phase 0)

- **Source** → **PlaceMention** → **Place** — places with provenance (who mentioned them),
  PostGIS `POINT` coordinates, and a `type` (restaurant / activity / hotel / other).
- **Trip** → **Stop** (meta: city stays) → **Day** → **ItineraryItem** (meal/activity/transit…).
- **Document** — a fetched page: cached raw HTML + extracted main text (Phase-1 ingestion output).
- **EditLog** — audit trail tagged by origin (laptop vs phone) for sync.

## What's next

- Connect a Postgres+PostGIS database (free Neon/Supabase) and run `alembic upgrade head`.
- Provide the three open inputs in [docs/SPEC.md](docs/SPEC.md): **budget**, **flights**, **seed blogs**.
- **Phase 2 — Extract/enrich:** categorize + geocode places, run graphify, load insights.
