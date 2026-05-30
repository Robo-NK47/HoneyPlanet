"""Research festivals & seasonal events for the trip windows and store them.

Uses Claude (Opus 4.8) + web search to get accurate 2026 dates, then writes Event rows
(replacing any existing ones).

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/find_events.py
"""

from __future__ import annotations

import asyncio
from datetime import date

import anthropic
from geoalchemy2.elements import WKTElement
from sqlalchemy import delete

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.enrich.events import research_events
from trip_planner.models import Event

REGIONS = [
    (
        "Japan",
        "Tokyo, Hakone, Kawaguchiko (Mt Fuji), Takayama, Kanazawa, Kyoto, "
        "Hiroshima/Miyajima, Osaka, Nara",
        "2026-11-10",
        "2026-12-10",
        "jp",
    ),
    (
        "Thailand",
        "Bangkok, Krabi/Railay, Koh Samui",
        "2026-12-10",
        "2026-12-30",
        "th",
    ),
]


def _parse_date(value: object) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


def _clip(value: object, length: int) -> str | None:
    if not value:
        return None
    return str(value)[:length]


def _point(lat: object, lng: object) -> WKTElement | None:
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        return WKTElement(f"POINT({lng} {lat})", srid=4326)
    return None


async def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in .env")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async with async_session_maker() as session:
        await session.execute(delete(Event))
        total = 0
        for label, cities, start, end, country in REGIONS:
            print(f"Researching events in {label} ({start} .. {end})…")
            events = await asyncio.to_thread(
                research_events, client, region_label=label, cities=cities, start=start, end=end
            )
            for e in events:
                session.add(
                    Event(
                        name=_clip(e.get("name"), 512) or "Event",
                        name_local=_clip(e.get("name_local"), 512),
                        description=e.get("description"),
                        category=_clip(e.get("category"), 32) or "festival",
                        city=_clip(e.get("city"), 128),
                        country=country,
                        venue=_clip(e.get("venue"), 256),
                        location=_point(e.get("lat"), e.get("lng")),
                        start_date=_parse_date(e.get("start_date")),
                        end_date=_parse_date(e.get("end_date")),
                        url=_clip(e.get("url"), 1024),
                        notes=e.get("notes"),
                    )
                )
                total += 1
            await session.commit()
            print(f"  stored {len(events)} events")
    print(f"Done. {total} events.")


if __name__ == "__main__":
    asyncio.run(main())
