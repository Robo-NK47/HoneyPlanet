"""Chat agent: Claude (Opus 4.8) with tools to read/modify the plan DB and search the web."""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import date

import anthropic
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from trip_planner.agents import (
    estimate_stop_budget,
    plan_transport,
    recommend_hotel,
)
from trip_planner.config import settings
from trip_planner.models import Day, Event, ItemKind, ItineraryItem, Place, Stop, Task, Trip
from trip_planner.plan.writer import parse_time

MODEL = "claude-opus-4-8"
GRAPH_PATH = "data/graphify-out/graph.json"  # built by scripts/build_graph.py (graphify)
TASK_TOOLS = {"add_task", "update_task", "delete_task"}

SYSTEM = (
    "You are the assistant for a couple's honeymoon (Japan 10 Nov–10 Dec 2026, then Thailand "
    "to 30 Dec 2026). You can READ and MODIFY the saved itinerary with tools, and search the "
    "web for current facts (hours, prices, events, closures). Be concise and warm.\n"
    "- Ground every answer in the real plan via the tools; do not invent itinerary details.\n"
    "- To change the plan, call the write tools (add_item / update_item / delete_item / "
    "move_item) and then briefly confirm exactly what you changed.\n"
    "- Use web_search for anything time-sensitive or not in the plan/place data.\n"
    "- Use query_graph to consult the knowledge graph graphify built from the scraped "
    "travel sources (how places, foods, and topics connect across the blogs/guides).\n"
    "- Delegate to the specialists when relevant: consult_hotel_expert (where to sleep), "
    "consult_transport_expert (how to get there / get around, with realistic times), and "
    "consult_budget_expert (what a city/day costs and how to spend less). They return advice "
    "in NIS (₪); apply their suggestions with the write tools when the user agrees.\n"
    "- Use list_events for festivals & seasonal events (autumn leaves, winter "
    "illuminations, matsuri); suggest building days around ones that overlap the dates.\n"
    "- Maintain the task board with add_task/update_task/delete_task — turn booking "
    "notices into dated tasks (book ryokan, reserve omakase, buy Shinkansen tickets).\n"
    "- Item ids come from get_day, task ids from list_tasks; reference them when editing."
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
        "name": "query_graph",
        "description": (
            "Query the knowledge graph graphify built over the scraped travel sources "
            "(blogs and guides) — discover how places, foods, and topics connect."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"question": {"type": "string"}},
            "required": ["question"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consult_hotel_expert",
        "description": (
            "Ask the hotel expert to find the best-value honeymoon stay for a place. "
            "Give the location and how many nights; it returns a hotel pick (with price in NIS)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "location": {"type": "string", "description": "City/area we sleep in"},
                "nights": {"type": "integer"},
                "area": {"type": "string", "description": "preferred neighborhood (optional)"},
                "budget_per_night_nis": {"type": "integer"},
                "notes": {"type": "string", "description": "anything to factor in"},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consult_transport_expert",
        "description": (
            "Ask the transport expert how to reach a place and get around it — precise, "
            "realistic times and costs (NIS), time- and budget-efficient."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "to_place": {"type": "string"},
                "from_place": {"type": "string", "description": "where we travel from (optional)"},
                "notes": {"type": "string", "description": "areas/spots to move between"},
            },
            "required": ["to_place"],
            "additionalProperties": False,
        },
    },
    {
        "name": "consult_budget_expert",
        "description": (
            "Ask the budget expert what a city (or the trip) costs and how to spend less for the "
            "same experience. Pass a city to estimate that stop's planned days; omit it for a "
            "whole-trip review."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"city": {"type": "string", "description": "stop name (optional)"}},
            "additionalProperties": False,
        },
    },
    {
        "name": "list_events",
        "description": "List festivals & seasonal events during the trip (dates and city).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
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
    {
        "name": "list_tasks",
        "description": "List every task on the board (ids, dates, importance, done status).",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "add_task",
        "description": "Add a task to the board (e.g. book a hotel, reserve a restaurant).",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "importance": {"type": "string", "enum": ["low", "medium", "high"]},
                "notes": {"type": "string"},
            },
            "required": ["title"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_task",
        "description": "Update a task by id (title, due_date, importance, done, notes).",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer"},
                "title": {"type": "string"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "importance": {"type": "string", "enum": ["low", "medium", "high"]},
                "done": {"type": "boolean"},
                "notes": {"type": "string"},
            },
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "delete_task",
        "description": "Delete a task by id.",
        "input_schema": {
            "type": "object",
            "properties": {"task_id": {"type": "integer"}},
            "required": ["task_id"],
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


async def _query_graph(question: str) -> str:
    if not os.path.exists(GRAPH_PATH):
        return "The knowledge graph isn't built yet (run scripts/build_graph.py)."
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "graphify", "query", question,
        "--graph", GRAPH_PATH, "--budget", "1200",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=60)
    except TimeoutError:
        proc.kill()
        return "Graph query timed out."
    text = out.decode("utf-8", "replace").strip() or err.decode("utf-8", "replace").strip()
    return text[:6000] or "(no graph result)"


async def _list_events(session: AsyncSession) -> str:
    rows = (await session.execute(select(Event).order_by(Event.start_date))).scalars().all()
    if not rows:
        return "No events on record."
    lines = []
    for e in rows:
        when = e.start_date.isoformat() if e.start_date else "?"
        if e.end_date and e.end_date != e.start_date:
            when += ".." + e.end_date.isoformat()
        lines.append(f"- {when} [{e.category}] {e.city}: {e.name}")
    return "\n".join(lines)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


async def _list_tasks(session: AsyncSession) -> str:
    rows = (await session.execute(select(Task))).scalars().all()
    if not rows:
        return "The task board is empty."
    lines = []
    for t in sorted(rows, key=lambda x: (x.due_date or date.max, x.id)):
        box = "[x]" if t.done else "[ ]"
        when = t.due_date.isoformat() if t.due_date else "no date"
        lines.append(f"{box} id={t.id} ({when}, {t.importance}) {t.title}")
    return "\n".join(lines)


async def _add_task(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    importance = inp.get("importance")
    if importance not in ("low", "medium", "high"):
        importance = "medium"
    task = Task(
        title=str(inp["title"])[:512],
        due_date=_parse_date(inp.get("due_date")),
        importance=importance,
        notes=inp.get("notes"),
        done=False,
    )
    session.add(task)
    await session.flush()
    return f"Added task id={task.id}: {task.title}", True


async def _update_task(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    task = await session.get(Task, inp["task_id"])
    if task is None:
        return "No such task.", False
    if inp.get("title") is not None:
        task.title = str(inp["title"])[:512]
    if inp.get("due_date") is not None:
        task.due_date = _parse_date(inp["due_date"])
    if inp.get("importance") in ("low", "medium", "high"):
        task.importance = inp["importance"]
    if inp.get("done") is not None:
        task.done = bool(inp["done"])
    if inp.get("notes") is not None:
        task.notes = inp["notes"]
    await session.flush()
    return f"Updated task {task.id}.", True


async def _delete_task(session: AsyncSession, inp: dict) -> tuple[str, bool]:
    task = await session.get(Task, inp["task_id"])
    if task is None:
        return "No such task.", False
    await session.delete(task)
    await session.flush()
    return f"Deleted task {inp['task_id']}.", True


def _serialize_days(days: list[Day]) -> str:
    lines: list[str] = []
    for day in sorted(days, key=lambda d: d.date):
        lines.append(f"{day.date} — {day.title or ''}")
        for it in sorted(day.items, key=lambda x: x.order_index):
            when = it.start_time.strftime("%H:%M") if it.start_time else "--:--"
            lines.append(f"  {when} [{it.kind.value}] {it.title or ''}")
    return "\n".join(lines)


def _fmt_hotel(h: dict) -> str:
    if not h.get("name"):
        return "The hotel expert couldn't settle on a pick — try giving an area or a budget."
    head = f"🏨 {h.get('name')}"
    if h.get("area"):
        head += f" — {h['area']}"
    price = f"₪{h.get('price_per_night_nis')}/night"
    if h.get("total_nis"):
        price += f" (total ₪{h.get('total_nis')})"
    if h.get("rating"):
        price += f" · ★{h.get('rating')}"
    lines = [head, price]
    if h.get("why"):
        lines.append(h["why"])
    if h.get("booking_url"):
        lines.append(f"Book: {h['booking_url']}")
    for a in (h.get("alternatives") or [])[:2]:
        lines.append(
            f"  alt: {a.get('name')} ₪{a.get('price_per_night_nis')} — {a.get('note', '')}"
        )
    return "\n".join(lines)


def _fmt_transport(t: dict) -> str:
    leg = t.get("arrival_leg") or {}
    ga = t.get("getting_around") or {}
    lines: list[str] = []
    if leg:
        book = f" · book: {leg['booking_notice']}" if leg.get("booking_notice") else ""
        lines.append(
            f"🚆 Arrival: {leg.get('mode')} from {leg.get('from')} "
            f"— ~{leg.get('duration_min')}min, ₪{leg.get('cost_nis')}, "
            f"depart ~{leg.get('depart_suggestion')}{book}"
        )
    if ga:
        pass_cost = f" (₪{ga.get('pass_cost_nis')})" if ga.get("pass_cost_nis") else ""
        lines.append(
            f"Getting around: {ga.get('summary', '')} Pass: {ga.get('recommended_pass', 'n/a')}"
            f"{pass_cost}"
        )
        for h in (ga.get("typical_legs") or [])[:5]:
            lines.append(
                f"  {h.get('from')}→{h.get('to')}: {h.get('mode')} {h.get('minutes')}min "
                f"₪{h.get('cost_nis')}"
            )
    return "\n".join(lines) or "No transport details returned."


def _fmt_budget(b: dict) -> str:
    lines = [f"Stop total ≈ ₪{b.get('stop_total_nis')}"]
    for d in (b.get("days") or [])[:14]:
        note = f" — {d.get('note')}" if d.get("note") else ""
        lines.append(f"  {d.get('date')}: ₪{d.get('est_cost_nis')}{note}")
    for tip in (b.get("savings_tips") or [])[:4]:
        lines.append(f"  💡 {tip}")
    return "\n".join(lines)


async def _consult_hotel(inp: dict) -> str:
    h = await recommend_hotel(
        stop_name=str(inp.get("location", "")),
        country="(infer from the location — Japan or Thailand)",
        area=inp.get("area"),
        nights=int(inp.get("nights") or 1),
        dates=[],
        places_summary=inp.get("notes") or "",
        budget_per_night_nis=int(inp.get("budget_per_night_nis") or 800),
    )
    return _fmt_hotel(h)


async def _consult_transport(inp: dict) -> str:
    t = await plan_transport(
        to_stop=str(inp.get("to_place", "")),
        country="(infer — Japan or Thailand)",
        dates=[],
        arrive_from=inp.get("from_place") or "(unspecified origin)",
        intra_areas=inp.get("notes") or "",
    )
    return _fmt_transport(t)


async def _consult_budget(session: AsyncSession, inp: dict) -> str:
    city = inp.get("city")
    if city:
        stop = (
            await session.execute(
                select(Stop)
                .where(Stop.name.ilike(f"%{city}%"))
                .options(
                    selectinload(Stop.days).selectinload(Day.items), selectinload(Stop.hotel)
                )
                .limit(1)
            )
        ).scalars().first()
        if stop is None:
            return f"No stop matching '{city}'."
        dates = sorted(d.date.isoformat() for d in stop.days)
        hotel = stop.hotel
        hotel_summary = (
            f"{hotel.name} ~₪{(hotel.tags or {}).get('price_per_night_nis')}/night"
            if hotel
            else "(none)"
        )
        b = await estimate_stop_budget(
            stop_name=stop.name,
            country="Japan" if stop.country == "jp" else "Thailand",
            dates=dates,
            plan_text=_serialize_days(stop.days),
            hotel_summary=hotel_summary,
            transport_summary="",
            total_budget_nis=50_000,
            spent_so_far_nis=0,
        )
        return _fmt_budget(b)
    rows = (await session.execute(select(Day).order_by(Day.date))).scalars().all()
    estimated = [d for d in rows if d.est_cost]
    if not estimated:
        return "No per-day estimates yet — run scripts/refresh_plan.py to generate them."
    total = sum(d.est_cost or 0 for d in rows)
    return (
        f"Estimated trip spend ≈ ₪{total} of ₪50,000 across {len(estimated)} estimated days. "
        "Ask about a specific city for a day-by-day breakdown and savings tips."
    )


async def _exec_tool(session: AsyncSession, name: str, inp: dict) -> tuple[str, bool]:
    if name == "get_plan_overview":
        return await _overview(session), False
    if name == "get_day":
        return await _get_day(session, inp["date"]), False
    if name == "find_places":
        result = await _find_places(session, inp.get("city"), inp.get("category"), inp.get("query"))
        return result, False
    if name == "query_graph":
        return await _query_graph(inp["question"]), False
    if name == "consult_hotel_expert":
        return await _consult_hotel(inp), False
    if name == "consult_transport_expert":
        return await _consult_transport(inp), False
    if name == "consult_budget_expert":
        return await _consult_budget(session, inp), False
    if name == "list_events":
        return await _list_events(session), False
    if name == "add_item":
        return await _add_item(session, inp)
    if name == "update_item":
        return await _update_item(session, inp)
    if name == "delete_item":
        return await _delete_item(session, inp)
    if name == "move_item":
        return await _move_item(session, inp)
    if name == "list_tasks":
        return await _list_tasks(session), False
    if name == "add_task":
        return await _add_task(session, inp)
    if name == "update_task":
        return await _update_task(session, inp)
    if name == "delete_task":
        return await _delete_task(session, inp)
    return f"Unknown tool: {name}", False


async def run_chat(
    session: AsyncSession, message: str, history: list[dict]
) -> tuple[str, bool, bool, list[dict]]:
    """Run one chat turn. Returns (reply, plan_changed, tasks_changed, updated_text_history)."""
    messages: list[dict] = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    messages.append({"role": "user", "content": message})

    tools = CUSTOM_TOOLS + [WEB_SEARCH_TOOL]
    reply = ""
    plan_changed = False
    tasks_changed = False

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
                if wrote:
                    if block.name in TASK_TOOLS:
                        tasks_changed = True
                    else:
                        plan_changed = True
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
    return reply or "(no reply)", plan_changed, tasks_changed, new_history
