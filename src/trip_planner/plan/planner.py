"""Day-by-day itinerary planner backed by Claude (Opus 4.8) with structured output."""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-4-8"

ItemKindLiteral = Literal["meal", "activity", "transit", "lodging", "free"]


class PlannedItem(BaseModel):
    kind: ItemKindLiteral
    title: str
    place_name: str | None = None  # match to a provided place by exact name when possible
    start_time: str | None = None  # "HH:MM"
    end_time: str | None = None
    transit_mode: str | None = None  # walk / train / subway / bus / car / ferry / flight
    transit_minutes: int | None = None
    notes: str | None = None
    booking_notice: str | None = None  # reservation / ticket to arrange in advance


class PlannedDay(BaseModel):
    date: str  # YYYY-MM-DD
    title: str
    summary: str | None = None
    items: list[PlannedItem]


class StopPlan(BaseModel):
    days: list[PlannedDay]


SYSTEM = """You are an expert honeymoon trip planner for Japan and Thailand. You design \
day-by-day itineraries that are realistic, well-paced, and delightful for a fit couple in \
their early-to-mid thirties who are adventurous eaters and love food, culture, and music.

Design principles:
- Food-first: every day has strong, specific meal choices (breakfast, lunch, dinner) drawing \
on the provided restaurants and food markets. Make notable food experiences the backbone.
- Balanced pace: about 2-3 main activities per day plus meals, with genuine breathing room. \
Do not over-pack; leave space to wander.
- Geographic sense: cluster places that are near each other on the same day and minimise \
back-and-forth. Add a `transit` item (with mode and minutes) whenever moving between areas \
or cities, including the arrival and onward legs.
- Use the PROVIDED places by their exact names where they fit (restaurants, attractions, \
theme parks, food markets). You may also add well-known specific spots from your own \
knowledge when they improve the day, but prefer the curated list.
- Booking notices: set `booking_notice` whenever something realistically needs advance \
action — popular or high-end restaurants (e.g. "reserve ~1 month ahead"), ryokan, timed-entry \
attractions (teamLab, Ghibli Museum, theme parks), and transport that needs tickets \
(Shinkansen, limited expresses like the Odakyu Romancecar, internal flights, island ferries).
- Times: give a `start_time` (HH:MM) for anchored items; keep the order sensible.

Return exactly one day entry per requested date, covering all of them."""


def _places_block(places: list[dict]) -> str:
    lines: list[str] = []
    for p in places:
        star = f" ★{p['rating']}" if p.get("rating") else ""
        lines.append(f"- {p['name']} — {p['category']}{star}")
    return "\n".join(lines) or "(no curated places provided; use your own expertise)"


def plan_stop(
    client: anthropic.Anthropic,
    *,
    stop_name: str,
    country: str,
    dates: list[str],
    places: list[dict],
    trip_notes: str,
) -> StopPlan:
    user = (
        f"Plan the stop: {stop_name} ({country}).\n"
        f"Dates to cover ({len(dates)} days), exactly one entry per date: {', '.join(dates)}.\n"
        f"The first date is arrival in {stop_name}; the final date may include departure to "
        f"the next stop.\n\n"
        f"Trip context: {trip_notes}\n\n"
        f"Curated top places here (use these by their exact name where they fit):\n"
        f"{_places_block(places)}\n\n"
        "Design the day-by-day itinerary now."
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=8000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=StopPlan,
    )
    return response.parsed_output
