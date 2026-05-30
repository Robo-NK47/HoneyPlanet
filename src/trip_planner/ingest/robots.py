"""robots.txt handling. Parsing is split from fetching so the policy logic is unit-testable."""

from __future__ import annotations

from urllib import robotparser
from urllib.parse import urlparse

# Identifies our crawler; contact lets site owners reach the trip's owner if needed.
DEFAULT_UA = "TripPlannerBot/0.1 (+honeymoon trip planner; contact: kahanobeats@gmail.com)"


def robots_url_for(url: str) -> str:
    parts = urlparse(url)
    return f"{parts.scheme}://{parts.netloc}/robots.txt"


def parser_from_text(robots_txt: str, base_url: str) -> robotparser.RobotFileParser:
    rp = robotparser.RobotFileParser()
    rp.set_url(robots_url_for(base_url))
    rp.parse(robots_txt.splitlines())
    return rp


def can_fetch(robots_txt: str | None, url: str, user_agent: str = DEFAULT_UA) -> bool:
    """Return True if `user_agent` may fetch `url`. No robots.txt ⇒ allowed."""
    if not robots_txt:
        return True
    return parser_from_text(robots_txt, url).can_fetch(user_agent, url)
