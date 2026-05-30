from __future__ import annotations

from trip_planner.agents.shared import extract_json_object
from trip_planner.web import _breakdown_html, _budget_banner, _hotel_html


def test_extract_json_object_handles_prose_and_fences() -> None:
    text = (
        "Here is the result:\n```json\n"
        '{"name": "X", "n": 3, "nested": {"a": [1, 2]}}\n```\nDone.'
    )
    obj = extract_json_object(text)
    assert obj["name"] == "X"
    assert obj["n"] == 3
    assert obj["nested"] == {"a": [1, 2]}


def test_extract_json_object_ignores_braces_inside_strings() -> None:
    text = 'noise {"label": "a } b", "ok": true} trailing'
    obj = extract_json_object(text)
    assert obj["label"] == "a } b"
    assert obj["ok"] is True


def test_extract_json_object_returns_empty_on_garbage() -> None:
    assert extract_json_object("no json here") == {}
    assert extract_json_object("{not valid}") == {}


def test_budget_banner_on_track_and_over() -> None:
    on = _budget_banner({"total_est": 25000, "budget": 50000})
    assert "₪25,000 / ₪50,000" in on
    assert "on track" in on
    assert "trim" not in on

    over = _budget_banner({"total_est": 60000, "budget": 50000})
    assert "bbar over" in over
    assert "trim" in over


def test_budget_banner_empty_without_estimate() -> None:
    assert _budget_banner({"total_est": 0, "budget": 50000}) == ""
    assert _budget_banner({}) == ""


def test_breakdown_html_skips_zero_categories() -> None:
    out = _breakdown_html(
        {"lodging": 800, "food": 400, "transport": 0, "activities": 0, "other": 0}
    )
    assert "lodging ₪800" in out
    assert "food ₪400" in out
    assert "transport" not in out
    assert _breakdown_html(None) == ""
    assert _breakdown_html({"lodging": 0}) == ""


def test_hotel_html_renders_link_and_price() -> None:
    out = _hotel_html(
        {
            "name": "Celestine",
            "area": "Gion",
            "price_per_night_nis": 1204,
            "url": "https://example.com",
            "why": "lovely",
        }
    )
    assert "Celestine" in out
    assert "₪1,204/night" in out
    assert "href=" in out
    assert _hotel_html(None) == ""
    assert _hotel_html({}) == ""
