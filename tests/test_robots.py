from __future__ import annotations

from trip_planner.ingest.robots import can_fetch

ROBOTS = """User-agent: *
Disallow: /private/
Allow: /
"""


def test_allows_public_path() -> None:
    assert can_fetch(ROBOTS, "https://example.com/blog/best-ramen") is True


def test_blocks_disallowed_path() -> None:
    assert can_fetch(ROBOTS, "https://example.com/private/secret") is False


def test_missing_robots_allows() -> None:
    assert can_fetch(None, "https://example.com/anything") is True
