"""Budget aggregation invariants: ground spend excludes international flights, and the grand
total counts ground + flights exactly once each (guards against the double-count regression)."""

from __future__ import annotations

from datetime import date

from trip_planner.models import Day, ItemKind, ItineraryItem, Stop, Trip
from trip_planner.plan.costs import INTL_FLIGHT, build_budget, collect_intl_flights


def _sample_trip() -> Trip:
    """A trip whose day.est_cost is on-the-ground only (flights live on their own items)."""
    trip = Trip(name="t", start_date=date(2026, 11, 10), end_date=date(2026, 12, 30))

    jp = Stop(country="jp")
    jp.id = 1
    d1 = Day(date=date(2026, 11, 10), est_cost=940)  # ground only (326 dinner + 614 lodging)
    d1.items = [
        ItineraryItem(
            kind=ItemKind.transit, transit_mode=INTL_FLIGHT, est_cost=4126, title="flight in"
        ),
        ItineraryItem(kind=ItemKind.meal, est_cost=326, title="dinner"),
    ]
    jp.days = [d1]

    th = Stop(country="th")
    th.id = 2
    d2 = Day(date=date(2026, 12, 29), est_cost=857)
    d2.items = [
        ItineraryItem(
            kind=ItemKind.transit, transit_mode=INTL_FLIGHT, est_cost=3880, title="flight home"
        ),
    ]
    th.days = [d2]

    trip.stops = [jp, th]
    return trip


def test_ground_excludes_flights_and_total_counts_each_once() -> None:
    budget, _ = build_budget(_sample_trip(), 50_000)
    assert budget["ground"] == 940 + 857  # stored day.est_cost — flights NOT included
    assert budget["flights_total"] == 4126 + 3880
    assert budget["total_est"] == 940 + 857 + 4126 + 3880  # each counted exactly once
    assert budget["budget"] == 50_000
    assert budget["by_country"] == {"jp": 940, "th": 857}
    assert budget["by_stop"] == {1: 940, 2: 857}


def test_collect_intl_flights_in_date_order() -> None:
    flights = collect_intl_flights(_sample_trip())
    assert [f["leg"] for f in flights] == ["flight in", "flight home"]
    assert [f["cost"] for f in flights] == [4126, 3880]
