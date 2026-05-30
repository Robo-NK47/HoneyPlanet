"""Persist a StopPlan into Day / ItineraryItem rows (shared by the planner and verifier)."""

from __future__ import annotations

from datetime import datetime, time

from sqlalchemy.ext.asyncio import AsyncSession

from trip_planner.models import Day, ItemKind, ItineraryItem
from trip_planner.plan.planner import StopPlan


def parse_time(value: str | None) -> time | None:
    if not value:
        return None
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    return None


async def apply_stop_plan(
    session: AsyncSession,
    days_by_date: dict[str, Day],
    places_by_name: dict[str, int],
    plan: StopPlan,
) -> int:
    """Replace the items of each planned day with freshly generated ones. Returns count."""
    written = 0
    for pday in plan.days:
        day = days_by_date.get(pday.date)
        if day is None:
            continue
        if pday.title:
            day.title = pday.title[:255]
        if pday.summary:
            day.summary = pday.summary
        for old in list(day.items):
            await session.delete(old)
        await session.flush()
        for idx, item in enumerate(pday.items):
            place_id = None
            if item.place_name:
                place_id = places_by_name.get(item.place_name.strip().lower())
            try:
                kind = ItemKind(item.kind)
            except ValueError:
                kind = ItemKind.activity
            session.add(
                ItineraryItem(
                    day_id=day.id,
                    place_id=place_id,
                    kind=kind,
                    title=item.title[:512],
                    start_time=parse_time(item.start_time),
                    end_time=parse_time(item.end_time),
                    order_index=idx,
                    transit_mode=(item.transit_mode[:128] if item.transit_mode else None),
                    transit_duration_min=item.transit_minutes,
                    notes=item.notes,
                    booking_notice=item.booking_notice,
                )
            )
            written += 1
    return written
