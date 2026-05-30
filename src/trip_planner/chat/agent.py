"""Chat agent: Claude (Opus 4.8) with tools to read/modify the plan DB and search the web."""

from __future__ import annotations

from datetime import date

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trip_planner.config import settings
from trip_planner.models import Day, ItemKind, ItineraryItem, Place, Trip
from trip_planner.plan.writer import parse_time

MODEL = "claude-opus-4-8"

SYSTEM = (
    "You are the assistant for a couple's honeymoon (Japan 10 Nov–10 Dec 2026, then Thailand "
    "to 30 Dec 2026). You can READ and MODIFY the saved itinerary with tools, and search the "
    "web for current facts (hours, prices, events, closures). Be concise and warm.\n"
    "- Ground every answer in the real plan via the tools; do not invent itinerary details.\n"
    "- To change the plan, call the write tools (add_item / update_item / delete_item / "
    "move_item) and then briefly confirm exactly what you changed.\n"
    "- Use web_search for anything time-sensitive or not in the plan/place data.\n"
    "- Item ids come from get_day; reference them when editing."
)

CUSTOM_TOOLS = [
    {
        "name": "get_plan_overview",
        "description": "List the trip's stops with their nights and dates.",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "get_day",
        "description": "Get the itinerary items (with ids) for one date.",
        "input_schema": {
            "type": "object",
            "properties": {"date": {"type": "string", "description": "YYYY-MM-DD"}},
            "required": ["date"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_places",
        "description": "Search known places (restaurants, attractions, theme parks, markets).",
        "input_schema": {
            "type": "object",
            "properties": {
                "city": {"type": "string"},
                "category": {
                    "type": "string",
                    "enum": ["restaurant", "attraction", "theme_park", "food_market"],
                },
                "query": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "add_item",
        "description": "Add an itinerary item to a date.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "title": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["meal", "activity", "transit", "lodging", "free"],
                },
                "start_time": {"type": "string", "description": "HH:MM"},
                "notes": {"type": "string"},
                "booking_notice": {"type": "string"},
            },
            "required": ["date", "title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_item",
        "description": "Update fields of an itinerary item by id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "title": {"type": "string"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "notes": {"type": "string"},
                "booking_notice": {"type": "string"},
                "kind": {
                    "type": "string",
                    "enum": ["meal", "activity", "transit", "lodging", "free"],
                },
            },
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_item",
        "description": "Delete an itinerary item by id.",
        "input_schema": {
            "type": "object",
            "properties": {"item_id": {"type": "integer"}},
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "move_item",
        "description": "Move an item to another date and/or reorder it.",
        "input_schema": {
            "type": "object",
            "properties": {
                "item_id": {"type": "integer"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "order_index": {"type": "integer"},
            },
            "required": ["item_id"],
            "additionalProperties": False,
        },
    },
]

WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}

client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key or "missing")


async def _overview(session: AsyncSession) -> str:
    trip = (
        await session.execute(select(Trip).options(selectinload(Trip.stops)).limit(1))
    ).scalars().first()
    if trip is None:
        return "No trip found."
    lines = [f"{trip.name} ({trip.start_date}..{trip.end_date})"]
    for s in trip.stops:
        lines.append(f"- {s.name}: {s.nights} nights, {s.arrival_date}..{s.departure_date}")
    return "\n".join(lines)


async def _get_day(session: AsyncSession, date_str: str) -> str:
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return f"Invalid date: {date_str}"
    day = (
        await session.execute(
            select(Day).where(Day.date == target).options(selectinload(Day.items))
        )
    ).scalars().first()
    if day is None:
        return f"No day at {date_str}."
    lines = [f"{day.date} — {day.title or ''}"]
    for it in sorted(day.items, key=lambda x: x.order_index):
        when = it.start_time.strftime("%H:%M") if it.start_time else "--:--"
        extra = ""
        if it.notes:
            extra += f" | notes: {it.notes}"
        if it.booking_notice:
            extra += f" | BOOK: {it.booking_notice}"
        lines.append(f"  id={it.id} {when} [{it.kind.value}] {it.title}{extra}")
    return "\n".join(lines)


async def _find_places(
    session: AsyncSession, city: str | None, category: str | None, query: str | None
) -> str:
    stmt = select(Place)
    if city:
        stmt = stmt.where(Place.city.ilike(f"%{city}%"))
    if category:
        stmt = stmt.where(Place.subtype == category)
    if query:
        stmt = stmt.where(Place.name.ilike(f"%{query}%"))
    stmt = stmt.order_by(Place.rating.desc().nulls_last()).limit(15)
    rows = (await session.execute(stmt)).scalars().all()
    if not rows:
        return "No matching places."
    return "\n".join(f"- {p.name} ({p.subtype}, {p.city}) ★{p.rating}" for p in rows)


async def _day_by_date(session: AsyncSession, date_str: str) -> Day | None:
    try:
        target = date.fromisoformat(date_str)
    except ValueError:
        return None
    return (await session.execute(select(Day).where(Day.date == target))).scalars().first()


async def _add_item(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    day = await _day_by_date(session, inp["date"])
    if day is None:
        return f"No day at {inp['date']}.", False
    max_order = await session.scalar(
        select(func.max(ItineraryItem.order_index)).where(ItineraryItem.day_id == day.id)
    )
    try:
        kind = ItemKind(inp.get("kind", "activity"))
    except ValueError:
        kind = ItemKind.activity
    item = ItineraryItem(
        day_id=day.id,
        kind=kind,
        title=str(inp["title"])[:512],
        start_time=parse_time(inp.get("start_time")),
        order_index=(max_order or 0) + 1,
        notes=inp.get("notes"),
        booking_notice=inp.get("booking_notice"),
    )
    session.add(item)
    await session.flush()
    return f"Added item id={item.id} to {inp['date']}.", True


async def _update_item(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    item = await session.get(ItineraryItem, inp["item_id"])
    if item is None:
        return "No such item.", False
    if inp.get("title") is not None:
        item.title = str(inp["title"])[:512]
    if inp.get("start_time") is not None:
        item.start_time = parse_time(inp["start_time"])
    if inp.get("notes") is not None:
        item.notes = inp["notes"]
    if inp.get("booking_notice") is not None:
        item.booking_notice = inp["booking_notice"]
    if inp.get("kind") is not None:
        try:
            item.kind = ItemKind(inp["kind"])
        except ValueError:
            pass
    await session.flush()
    return f"Updated item {item.id}.", True


async def _delete_item(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    item = await session.get(ItineraryItem, inp["item_id"])
    if item is None:
        return "No such item.", False
    await session.delete(item)
    await session.flush()
    return f"Deleted item {inp['item_id']}.", True


async def _move_item(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    item = await session.get(ItineraryItem, inp["item_id"])
    if item is None:
        return "No such item.", False
    if inp.get("date"):
        day = await _day_by_date(session, inp["date"])
        if day is None:
            return f"No day at {inp['date']}.", False
        item.day_id = day.id
    if inp.get("order_index") is not None:
        item.order_index = inp["order_index"]
    await session.flush()
    return f"Moved item {item.id}.", True


async def _exec_tool(session: AsyncSession, name: str, inp: dict) -> tuple[str, bool]:
    if name == "get_plan_overview":
        return await _overview(session), False
    if name == "get_day":
        return await _get_day(session, inp["date"]), False
    if name == "find_places":
        result = await _find_places(session, inp.get("city"), inp.get("category"), inp.get("query"))
        return result, False
    if name == "add_item":
        return await _add_item(session, inp)
    if name == "update_item":
        return await _update_item(session, inp)
    if name == "delete_item":
        return await _delete_item(session, inp)
    if name == "move_item":
        return await _move_item(session, inp)
    return f"Unknown tool: {name}", False


async def run_chat(
    session: AsyncSession, message: str, history: list[dict]
) -> tuple[str, bool, list[dict]]:
    """Run one chat turn. Returns (reply, plan_changed, updated_text_history)."""
    messages: list[dict] = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": message})

    tools = CUSTOM_TOOLS + [WEB_SEARCH_TOOL]
    reply = ""
    changed = False

    for _ in range(8):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM,
            messages=messages,
            tools=tools,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        if text:
            reply = text

        if response.stop_reason == "end_turn":
            break
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in response.content:
            if block.type == "tool_use":
                out, wrote = await _exec_tool(session, block.name, dict(block.input))
                changed = changed or wrote
                results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": out}
                )
        if not results:
            break
        messages.append({"role": "user", "content": results})

    new_history = [
        *[m for m in history if m.get("role") in ("user", "assistant") and m.get("content")],
        {"role": "user", "content": message},
        {"role": "assistant", "content": reply or "(no reply)"},
    ]
    return reply or "(no reply)", changed, new_history
