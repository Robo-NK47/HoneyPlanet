"""Verify each stop's itinerary with Claude and auto-fix flagged problems.

For every stop: review the current plan; if there are medium/high problems, re-plan that stop
with the reviewer's fixes folded in, then re-verify once.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/verify_plan.py
"""

from __future__ import annotations

import asyncio

import anthropic
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, Place, Stop, Trip
from trip_planner.plan.planner import StopPlan, plan_stop
from trip_planner.plan.verifier import VerifyResult, verify_stop
from trip_planner.plan.writer import apply_stop_plan


def _serialize_day(date_str: str, title: str, items: list) -> list[str]:
    lines = [f"{date_str} — {title or ''}"]
    for it in items:
        when = it["time"] or "--:--"
        extra = []
        if it["transit_mode"]:
            extra.append(f"{it['transit_mode']} {it['transit_minutes'] or ''}min".strip())
        if it["notes"]:
            extra.append(it["notes"])
        if it["booking_notice"]:
            extra.append(f"BOOK: {it['booking_notice']}")
        suffix = (" — " + " | ".join(extra)) if extra else ""
        lines.append(f"  {when} [{it['kind']}] {it['title']}{suffix}")
    return lines


def serialize_stop(stop: Stop) -> str:
    lines: list[str] = []
    for day in sorted(stop.days, key=lambda d: d.date):
        items = [
            {
                "time": it.start_time.strftime("%H:%M") if it.start_time else None,
                "kind": it.kind.value,
                "title": it.title or "",
                "transit_mode": it.transit_mode,
                "transit_minutes": it.transit_duration_min,
                "notes": it.notes,
                "booking_notice": it.booking_notice,
            }
            for it in sorted(day.items, key=lambda x: x.order_index)
        ]
        lines += _serialize_day(day.date.isoformat(), day.title or "", items)
    return "\n".join(lines)


def serialize_plan(plan: StopPlan) -> str:
    lines: list[str] = []
    for d in plan.days:
        items = [
            {
                "time": it.start_time,
                "kind": it.kind,
                "title": it.title,
                "transit_mode": it.transit_mode,
                "transit_minutes": it.transit_minutes,
                "notes": it.notes,
                "booking_notice": it.booking_notice,
            }
            for it in d.items
        ]
        lines += _serialize_day(d.date, d.title or "", items)
    return "\n".join(lines)


def _serious(result: VerifyResult) -> list:
    return [p for p in result.problems if p.severity in ("high", "medium")]


async def main() -> None:
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in .env")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async with async_session_maker() as session:
        trip = (
            await session.execute(
                select(Trip)
                .options(selectinload(Trip.stops).selectinload(Stop.days).selectinload(Day.items))
                .order_by(Trip.id)
                .limit(1)
            )
        ).scalars().first()
        if trip is None:
            raise SystemExit("No trip found; run scripts/seed_plan.py first")

        places = (await session.execute(select(Place))).scalars().all()
        by_stop: dict[int, list[Place]] = {}
        for place in places:
            sid = (place.tags or {}).get("stop_id")
            if sid is not None:
                by_stop.setdefault(sid, []).append(place)

        for stop in trip.stops:
            country = "Japan" if stop.country == "jp" else "Thailand"
            result = await asyncio.to_thread(
                verify_stop,
                client,
                stop_name=stop.name,
                country=country,
                plan_text=serialize_stop(stop),
            )
            issues = _serious(result)
            if not issues:
                print(f"  {stop.name}: OK — {result.summary[:70]}")
                continue

            print(f"  {stop.name}: {len(issues)} issue(s) — re-planning with fixes")
            for p in issues:
                print(f"      [{p.severity}] {p.day_date}: {p.issue[:80]}")

            stop_places = by_stop.get(stop.id, [])
            place_dicts = [
                {
                    "name": p.name,
                    "category": (p.tags or {}).get("category") or p.subtype or "place",
                    "rating": p.rating,
                }
                for p in stop_places
            ]
            places_by_name = {p.name.strip().lower(): p.id for p in stop_places}
            days_by_date = {d.date.isoformat(): d for d in stop.days}
            fixes = "\n".join(
                f"- [{p.severity}] {p.day_date}: {p.issue} => FIX: {p.fix}" for p in issues
            )
            plan = await asyncio.to_thread(
                plan_stop,
                client,
                stop_name=stop.name,
                country=country,
                dates=sorted(days_by_date),
                places=place_dicts,
                trip_notes=trip.notes or "",
                fixes=fixes,
            )
            await apply_stop_plan(session, days_by_date, places_by_name, plan)
            await session.commit()

            recheck = await asyncio.to_thread(
                verify_stop,
                client,
                stop_name=stop.name,
                country=country,
                plan_text=serialize_plan(plan),
            )
            print(f"      -> {len(_serious(recheck))} serious issue(s) remaining after fix")

    print("Verification complete.")


if __name__ == "__main__":
    asyncio.run(main())
