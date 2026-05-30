"""Per-stop place enrichment: top restaurants / attractions / theme parks / food markets."""

from __future__ import annotations

import math

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trip_planner.enrich.google_places import PlaceResult, text_search
from trip_planner.models import Place, PlaceType, Stop

COUNTRY_NAME = {"jp": "Japan", "th": "Thailand"}

# (category tag, query template, PlaceType, how many to keep)
CATEGORIES = [
    ("restaurant", "top rated restaurants in {city}, {country}", PlaceType.restaurant, 5),
    ("attraction", "top tourist attractions in {city}, {country}", PlaceType.activity, 5),
    ("theme_park", "theme parks and amusement parks in {city}, {country}", PlaceType.activity, 5),
    ("food_market", "food markets in {city}, {country}", PlaceType.activity, 5),
]


def _clean_city(name: str) -> str:
    for sep in ("&", "/", "—", " - "):
        if sep in name:
            return name.split(sep)[0].strip()
    return name.strip()


def _score(r: PlaceResult) -> float:
    if r.rating is None:
        return 0.0
    return r.rating * math.log10(max(r.reviews, 1) + 1)


def _rank(results: list[PlaceResult], top_n: int, min_reviews: int = 20) -> list[PlaceResult]:
    eligible = [r for r in results if r.rating is not None and r.reviews >= min_reviews]
    eligible.sort(key=_score, reverse=True)
    return eligible[:top_n]


async def enrich_stop_places(
    session: AsyncSession, client: httpx.AsyncClient, api_key: str, stop: Stop
) -> int:
    city = _clean_city(stop.name)
    country = COUNTRY_NAME.get(stop.country or "", "")
    region = (stop.country or "").upper() or None
    added = 0
    for category, template, ptype, top_n in CATEGORIES:
        query = template.format(city=city, country=country)
        try:
            results = await text_search(client, api_key, query, region=region)
        except httpx.HTTPStatusError as exc:
            print(f"  ! {category}: HTTP {exc.response.status_code} {exc.response.text[:160]}")
            continue
        except httpx.HTTPError as exc:
            print(f"  ! {category}: {exc}")
            continue

        for rank, r in enumerate(_rank(results, top_n), start=1):
            if not r.place_id:
                continue
            existing = await session.scalar(
                select(Place).where(Place.google_place_id == r.place_id)
            )
            if existing is not None:
                continue
            session.add(
                Place(
                    name=r.name,
                    type=ptype,
                    subtype=category,
                    city=city,
                    country=stop.country,
                    address=r.address,
                    location=WKTElement(f"POINT({r.lng} {r.lat})", srid=4326),
                    google_place_id=r.place_id,
                    rating=r.rating,
                    price_level=r.price_level,
                    geocode_source="google",
                    geocode_confidence=1.0,
                    tags={
                        "category": category,
                        "rank": rank,
                        "stop_id": stop.id,
                        "stop_name": stop.name,
                        "website": r.website,
                        "maps_uri": r.maps_uri,
                    },
                    extra={"reviews": r.reviews, "primary_type": r.primary_type, "types": r.types},
                )
            )
            added += 1
    return added
