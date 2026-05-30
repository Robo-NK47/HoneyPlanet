"""Refresh the whole plan with the specialist agents (hotel, transport, budget).

For each stop, in order:
  1. Transport expert  -> arrival leg (precise time/cost) + getting-around plan
  2. Hotel expert      -> best-value honeymoon stay (saved as a Place, linked to the stop)
  3. Planner           -> re-plan the days, honoring the hotel + transit advisories
  4. Budget expert     -> per-day spend estimate (NIS) written onto each Day
Finally a trip-level budget review. Booking to-dos land on the task board.

All experts can consult the graphify knowledge graph and the live web.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/refresh_plan.py
"""

from __future__ import annotations

import asyncio
import sys

import anthropic
from geoalchemy2.elements import WKTElement
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from trip_planner.agents import (
    estimate_stop_budget,
    plan_transport,
    recommend_hotel,
    review_trip_budget,
)
from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Day, Place, PlaceType, Stop, Task, Trip
from trip_planner.plan.planner import StopPlan, plan_stop
from trip_planner.plan.writer import apply_stop_plan

TOTAL_BUDGET_NIS = 50_000
TASK_SENTINEL = "[expert]"  # auto-generated tasks; cleared & rewritten on each refresh


def _log(msg: str) -> None:
    print(msg, flush=True)


def _num(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


def _int(value: object, default: int = 0) -> int:
    return int(value) if isinstance(value, int | float) else default


def _serialize_plan(plan: StopPlan) -> str:
    lines: list[str] = []
    for d in plan.days:
        lines.append(f"{d.date} — {d.title or ''}")
        for it in d.items:
            when = it.start_time or "--:--"
            extra = []
            if it.transit_mode:
                extra.append(f"{it.transit_mode} {it.transit_minutes or ''}min".strip())
            if it.booking_notice:
                extra.append(f"BOOK: {it.booking_notice}")
            suffix = (" — " + " | ".join(extra)) if extra else ""
            lines.append(f"  {when} [{it.kind}] {it.title}{suffix}")
    return "\n".join(lines)


async def _save_hotel(session, stop: Stop, hotel: dict) -> str | None:
    name = hotel.get("name")
    if not name:
        return None
    place = await session.get(Place, stop.hotel_place_id) if stop.hotel_place_id else None
    if place is None:
        place = Place(type=PlaceType.hotel)
        session.add(place)
    place.name = str(name)[:512]
    place.type = PlaceType.hotel
    place.subtype = "hotel"
    place.country = stop.country
    place.city = stop.name[:128]
    area = hotel.get("area")
    place.area = str(area)[:128] if area else (stop.area or None)
    place.rating = _num(hotel.get("rating"))
    lat, lng = hotel.get("lat"), hotel.get("lng")
    if isinstance(lat, int | float) and isinstance(lng, int | float):
        place.location = WKTElement(f"POINT({lng} {lat})", srid=4326)
    place.tags = {
        "category": "hotel",
        "price_per_night_nis": hotel.get("price_per_night_nis"),
        "total_nis": hotel.get("total_nis"),
        "why": hotel.get("why"),
        "website": hotel.get("booking_url"),
        "alternatives": hotel.get("alternatives"),
    }
    await session.flush()
    stop.hotel_place_id = place.id
    return place.name


def _advisories(hotel: dict, transport: dict, daily_target_nis: int) -> str:
    leg = transport.get("arrival_leg") or {}
    ga = transport.get("getting_around") or {}
    hops = "; ".join(
        f"{h.get('from')}→{h.get('to')} {h.get('mode')} {h.get('minutes')}min"
        for h in (ga.get("typical_legs") or [])[:5]
    )
    book = f" Book: {leg['booking_notice']}" if leg.get("booking_notice") else ""
    parts = []
    if hotel.get("name"):
        parts.append(
            f"HOTEL: {hotel['name']} in {hotel.get('area', '')} "
            f"(~₪{hotel.get('price_per_night_nis', '?')}/night). Anchor the day near here."
        )
    if leg:
        parts.append(
            f"ARRIVAL: {leg.get('mode', 'travel')} from {leg.get('from', 'previous stop')} — "
            f"~{leg.get('duration_min', '?')} min door-to-door, depart "
            f"~{leg.get('depart_suggestion', 'morning')}.{book}"
        )
    if ga:
        parts.append(
            f"GETTING AROUND: {ga.get('summary', '')} Pass: {ga.get('recommended_pass', 'n/a')}. "
            f"Typical hops: {hops}"
        )
    parts.append(f"BUDGET: keep each day near ₪{daily_target_nis} for two; cut waste, not joy.")
    return "\n".join(parts)


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

        # Clear previously auto-generated tasks so a re-run doesn't pile up duplicates.
        await session.execute(delete(Task).where(Task.notes.like(f"{TASK_SENTINEL}%")))
        await session.commit()

        stops = list(trip.stops)
        stop_dates = {s.id: sorted(d.date.isoformat() for d in s.days) for s in stops}
        total_days_from = {}
        running = 0
        for s in reversed(stops):
            running += len(stop_dates[s.id])
            total_days_from[s.id] = running

        spent = 0
        stop_costs: list[dict] = []

        for idx, stop in enumerate(stops):
            dates = stop_dates[stop.id]
            if not dates:
                continue
            country = "Japan" if stop.country == "jp" else "Thailand"
            stop_places = by_stop.get(stop.id, [])
            place_names = ", ".join(p.name for p in stop_places[:6]) or stop.area or stop.name
            prev_stop = stops[idx - 1] if idx > 0 else None
            if prev_stop is None:
                arrive_from = "Tel Aviv (TLV), arrival flight"
            elif prev_stop.country == stop.country:
                arrive_from = prev_stop.name
            else:
                arrive_from = f"{prev_stop.name} (international flight)"
            remaining_days = max(1, total_days_from[stop.id])
            daily_target = int((TOTAL_BUDGET_NIS - spent) / remaining_days)
            per_night = max(150, min(2500, int(daily_target * 0.40)))

            _log(f"\n=== {stop.name} ({country}, {len(dates)} days) ===")

            # 1. Transport expert
            _log("  · transport expert…")
            transport = await plan_transport(
                to_stop=stop.name,
                country=country,
                dates=dates,
                arrive_from=arrive_from,
                intra_areas=place_names,
            )
            leg = transport.get("arrival_leg") or {}
            if leg:
                _log(
                    f"    arrival: {leg.get('mode')} ~{leg.get('duration_min')}min "
                    f"₪{leg.get('cost_nis')}"
                )

            # 2. Hotel expert
            _log("  · hotel expert…")
            place_summary = "\n".join(
                f"- {p.name} ({(p.tags or {}).get('category') or p.subtype or 'place'})"
                for p in stop_places[:10]
            )
            hotel = await recommend_hotel(
                stop_name=stop.name,
                country=country,
                area=stop.area,
                nights=stop.nights or len(dates),
                dates=dates,
                places_summary=place_summary,
                budget_per_night_nis=per_night,
            )
            hotel_name = await _save_hotel(session, stop, hotel)
            if hotel_name:
                _log(f"    hotel: {hotel_name} (~₪{hotel.get('price_per_night_nis')}/night)")

            # 3. Re-plan the stop honoring the advisories
            _log("  · planner (re-plan with advisories)…")
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
            advisories = _advisories(hotel, transport, daily_target)
            plan = await asyncio.to_thread(
                plan_stop,
                client,
                stop_name=stop.name,
                country=country,
                dates=dates,
                places=place_dicts,
                trip_notes=trip.notes or "",
                advisories=advisories,
            )
            written = await apply_stop_plan(session, days_by_date, places_by_name, plan)
            _log(f"    {written} items")

            # 4. Budget expert -> per-day estimates
            _log("  · budget expert…")
            hotel_summary = (
                f"{hotel.get('name')} ~₪{hotel.get('price_per_night_nis')}/night"
                if hotel.get("name")
                else "(none)"
            )
            transport_summary = (
                f"arrival {leg.get('mode')} ₪{leg.get('cost_nis')}; "
                f"around: {(transport.get('getting_around') or {}).get('recommended_pass', 'n/a')}"
            )
            budget = await estimate_stop_budget(
                stop_name=stop.name,
                country=country,
                dates=dates,
                plan_text=_serialize_plan(plan),
                hotel_summary=hotel_summary,
                transport_summary=transport_summary,
                total_budget_nis=TOTAL_BUDGET_NIS,
                spent_so_far_nis=spent,
            )
            stop_total = 0
            for d in budget.get("days") or []:
                day = days_by_date.get(d.get("date"))
                if day is None:
                    continue
                day.est_cost = _int(d.get("est_cost_nis"))
                bd = d.get("breakdown") or {}
                day.cost_breakdown = {
                    k: _int(bd.get(k))
                    for k in ("lodging", "food", "transport", "activities", "other")
                }
                stop_total += day.est_cost
            stop_total = _int(budget.get("stop_total_nis")) or stop_total
            _log(f"    stop spend ≈ ₪{stop_total}")

            # Booking to-dos on the task board
            if hotel.get("name"):
                session.add(
                    Task(
                        title=f"Book hotel: {hotel['name']} ({stop.name})",
                        notes=f"{TASK_SENTINEL} ₪{hotel.get('price_per_night_nis')}/night · "
                        f"{hotel.get('booking_url') or ''} · {hotel.get('why') or ''}",
                        importance="high",
                        done=False,
                    )
                )
            if leg.get("booking_notice"):
                session.add(
                    Task(
                        title=f"Book transport: {leg.get('mode')} → {stop.name}",
                        notes=f"{TASK_SENTINEL} {leg.get('booking_notice')}",
                        importance="medium",
                        done=False,
                    )
                )

            await session.commit()
            spent += stop_total
            stop_costs.append(
                {"stop": stop.name, "total_nis": stop_total, "days": len(dates)}
            )

        # Trip-level budget review
        _log("\n=== trip budget review ===")
        review = await review_trip_budget(
            total_budget_nis=TOTAL_BUDGET_NIS, stop_costs=stop_costs
        )
        est_total = _int(review.get("estimated_total_nis")) or spent
        _log(f"  estimated total ≈ ₪{est_total} / ₪{TOTAL_BUDGET_NIS}")
        _log(f"  verdict: {review.get('verdict', '')}")
        for action in (review.get("top_actions") or [])[:4]:
            session.add(
                Task(
                    title=action[:512],
                    notes=f"{TASK_SENTINEL} budget action",
                    importance="medium",
                    done=False,
                )
            )
        await session.commit()

    _log("\nRefresh complete.")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
