"""Single source of truth for trip cost aggregation (the live /plan budget).

Invariant: ``day.est_cost`` is a day's **on-the-ground** spend — food + activities + local
transit + that night's lodging — and ALWAYS excludes international flights. Booked flights
live on their own items (``transit_mode == INTL_FLIGHT``) and are shown in a separate Flights
section. The aggregation here adds the flights back exactly once on top of the ground total,
so the grand total is never double-counted.

A DB audit on 2026-06-13 confirmed the stored data already honours this: ground ₪45,777 +
flights ₪9,125 = ₪54,902, with no flight fare baked into any ``day.est_cost``.
"""

from __future__ import annotations

from trip_planner.models import Trip

INTL_FLIGHT = "international-flight"  # transit_mode sentinel for a booked international flight


def aggregate_ground(trip: Trip) -> tuple[dict[int, int], dict[str, int], int]:
    """Roll up stored ``day.est_cost`` (which excludes flights) into per-stop, per-country, and
    grand on-the-ground totals."""
    by_stop: dict[int, int] = {}
    by_country: dict[str, int] = {}
    ground = 0
    for stop in trip.stops:
        cost = sum(d.est_cost or 0 for d in stop.days)
        by_stop[stop.id] = cost
        code = stop.country or "?"
        by_country[code] = by_country.get(code, 0) + cost
        ground += cost
    return by_stop, by_country, ground


def collect_intl_flights(trip: Trip) -> list[dict]:
    """The booked international flights, in date order, for the Flights section."""
    flights: list[dict] = []
    for stop in trip.stops:
        for day in sorted(stop.days, key=lambda d: d.date):
            for it in day.items:
                if it.transit_mode == INTL_FLIGHT:
                    flights.append(
                        {
                            "leg": it.title or "",
                            "cost": it.est_cost or 0,
                            "date": day.date.isoformat(),
                        }
                    )
    return flights


def build_budget(trip: Trip, total_budget_nis: int) -> tuple[dict, list[dict]]:
    """Return ``(budget, flights)`` for the viewer.

    ``budget.total_est`` = ground spend + flights, counted exactly once each.
    """
    by_stop, by_country, ground = aggregate_ground(trip)
    flights = collect_intl_flights(trip)
    flights_total = sum(f["cost"] for f in flights)
    budget = {
        "total_est": ground + flights_total,
        "budget": total_budget_nis,
        "by_stop": by_stop,
        "by_country": by_country,
        "ground": ground,
        "flights_total": flights_total,
    }
    return budget, flights
