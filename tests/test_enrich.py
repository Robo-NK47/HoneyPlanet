from __future__ import annotations

from trip_planner.enrich.google_places import PRICE_LEVELS, PlaceResult
from trip_planner.enrich.seed_places import _clean_city, _rank


def test_clean_city() -> None:
    assert _clean_city("Hiroshima & Miyajima") == "Hiroshima"
    assert _clean_city("Krabi / Railay") == "Krabi"
    assert _clean_city("Tokyo") == "Tokyo"


def _pr(name: str, rating: float | None, reviews: int, pid: str) -> PlaceResult:
    return PlaceResult(
        place_id=pid, name=name, address=None, lat=0.0, lng=0.0, rating=rating,
        reviews=reviews, price_level=None, website=None, maps_uri=None,
        primary_type=None, types=[],
    )


def test_rank_orders_by_rating_and_review_volume() -> None:
    results = [
        _pr("a", 4.9, 100, "1"),
        _pr("b", 4.7, 5000, "2"),
        _pr("c", None, 100, "3"),  # no rating -> excluded
        _pr("d", 4.2, 1000, "4"),
        _pr("e", 5.0, 3, "5"),  # too few reviews -> excluded
    ]
    top = _rank(results, top_n=2, min_reviews=20)
    assert [r.name for r in top] == ["b", "d"]


def test_price_levels() -> None:
    assert PRICE_LEVELS["PRICE_LEVEL_MODERATE"] == 2
    assert PRICE_LEVELS["PRICE_LEVEL_VERY_EXPENSIVE"] == 4
