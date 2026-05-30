# Honeymoon Trip Planner — Requirements v1

The single source of truth for what we're building. Update as decisions change.

## The trip
- 🇯🇵 **Japan (deep data):** 10 Nov → 10 Dec 2026 (~30 days).
- 🇹🇭 **Thailand (light):** 10 Dec → 30 Dec 2026 (~20 days) — Bangkok + islands/beaches.
- **Travelers:** Nadav (35) + wife (32), fit, adventurous eaters, no dietary limits.
- **Style:** balanced pace (~2–3 anchors/day), **food-first**, with culture / music / nature as strong secondary.
- **Budget:** comfort baseline + deliberate splurges; total trip number _TBD_.
- **Flights:** booked (details _TBD_). **Hotels:** open → planner recommends cities → neighborhoods → hotels.

## What the system does
1. **Scrape** Israeli + international travel blogs/sources about Japan (seed list + discovery).
2. **Categorize** each place by **location** (PostGIS coordinates) and **type** (restaurant / activity / hotel / other).
3. **Knowledge graph** of the corpus via [graphify](https://github.com/safishamsi/graphify) — used as an insight/enrichment layer (clusters → areas/themes, hub places, relationship queries). The structured places live in Postgres.
4. **Plan** at two levels:
   - **Meta:** city/region sequence + nights, anchored to booked flights; hotel-area recommendations.
   - **Per-day:** geo-clustered daily itineraries (food anchors first, then secondary interests), with opening hours and transit times.
5. **Offline view** on a Samsung Galaxy S24 Ultra (PWA: service worker + IndexedDB + offline map tiles).
6. **Online editing** from the phone, syncing back to the backend.

## Architecture
- **Backend:** Python + FastAPI.
- **System of record:** PostgreSQL + PostGIS.
- **Knowledge graph:** graphify over the scraped corpus → mined into tags/edges in Postgres.
- **Scraping:** httpx + trafilatura (clean article extraction, Hebrew-friendly), robots.txt-respecting, raw cache.
- **Extract & categorize:** Claude (Anthropic) for place extraction + typing.
- **Geocoding (hybrid):** free Nominatim first → Google Places fallback (coords + ratings/hours/price).
- **Frontend:** PWA (React + Vite), offline view via service worker + IndexedDB + MapLibre tiles; online edit with a sync queue. **Bilingual EN/HE (RTL).**
- **Hosting:** managed cloud (Fly.io + managed Postgres). Light shared auth (two users).

## Build phases
0. **Scaffold** — FastAPI + Postgres/PostGIS skeleton, schema, config, API-key guides. ✅
1. **Ingest** — source registry, scraper, raw-HTML cache, Alembic migrations. ✅
2. **Extract / enrich** — categorize + geocode places; run graphify; load insights. ← _current_
3. **Plan: meta** — city sequence + nights + hotel-area picks.
4. **Plan: per-day** — daily itineraries with routing + hours.
5. **PWA** — offline view, then online edit + sync; bilingual UI.
6. **Deploy** — managed cloud; load the real Japan plan.

## Open inputs
- [ ] Total trip budget (USD or ILS).
- [ ] Flight details: Japan arrival (airport + datetime); Japan→Thailand (10 Dec, from/to airports); Thailand→home (30 Dec); home airport.
- [ ] Seed blogs/sources to prioritize.
