"""Minimal client for the Google Places API (New) Text Search endpoint."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.userRatingCount",
        "places.priceLevel",
        "places.websiteUri",
        "places.googleMapsUri",
        "places.primaryType",
        "places.types",
    ]
)
PRICE_LEVELS = {
    "PRICE_LEVEL_FREE": 0,
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}


@dataclass
class PlaceResult:
    place_id: str
    name: str
    address: str | None
    lat: float
    lng: float
    rating: float | None
    reviews: int
    price_level: int | None
    website: str | None
    maps_uri: str | None
    primary_type: str | None
    types: list[str]


async def text_search(
    client: httpx.AsyncClient,
    api_key: str,
    query: str,
    *,
    language: str = "en",
    region: str | None = None,
) -> list[PlaceResult]:
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": FIELD_MASK,
    }
    body: dict = {"textQuery": query, "languageCode": language}
    if region:
        body["regionCode"] = region
    resp = await client.post(SEARCH_URL, headers=headers, json=body, timeout=20)
    resp.raise_for_status()

    results: list[PlaceResult] = []
    for p in resp.json().get("places", []):
        loc = p.get("location") or {}
        if "latitude" not in loc or "longitude" not in loc:
            continue
        results.append(
            PlaceResult(
                place_id=p.get("id", ""),
                name=(p.get("displayName") or {}).get("text", ""),
                address=p.get("formattedAddress"),
                lat=loc["latitude"],
                lng=loc["longitude"],
                rating=p.get("rating"),
                reviews=p.get("userRatingCount") or 0,
                price_level=PRICE_LEVELS.get(p.get("priceLevel")),
                website=p.get("websiteUri"),
                maps_uri=p.get("googleMapsUri"),
                primary_type=p.get("primaryType"),
                types=p.get("types") or [],
            )
        )
    return results
