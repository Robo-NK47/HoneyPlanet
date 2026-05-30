"""Research festivals & seasonal events for a date window via Claude + web search."""

from __future__ import annotations

import json

import anthropic

MODEL = "claude-opus-4-8"
WEB_SEARCH = {"type": "web_search_20260209", "name": "web_search"}


def _parse_events(text: str) -> list[dict]:
    """Extract the first balanced JSON array from the model's text reply."""
    start = text.find("[")
    if start == -1:
        return []
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    parsed = json.loads(text[start : i + 1])
                    return parsed if isinstance(parsed, list) else []
                except json.JSONDecodeError:
                    return []
    return []


def research_events(
    client: anthropic.Anthropic, *, region_label: str, cities: str, start: str, end: str
) -> list[dict]:
    user = (
        f"Find real festivals and seasonal events happening in {region_label} between {start} "
        f"and {end} (year 2026), in or near these areas: {cities}. Include traditional matsuri, "
        f"seasonal highlights (autumn-leaf viewing, winter illuminations), notable markets, and "
        f"cultural events worth attending on a honeymoon. Use web search to confirm accurate 2026 "
        f"dates. Then output ONLY a JSON array (no prose, no markdown fences) where each object "
        f"has: name, name_local, category (one of festival|seasonal|illumination|market|cultural), "
        f"city, venue, lat, lng, start_date (YYYY-MM-DD), end_date (YYYY-MM-DD), description "
        f"(one concise sentence), notes (tickets/access if relevant). Only include events that "
        f"overlap {start}..{end}. lat and lng are decimal degrees for the venue."
    )
    messages: list[dict] = [{"role": "user", "content": user}]
    final_text = ""
    for _ in range(6):
        resp = client.messages.create(
            model=MODEL, max_tokens=8000, messages=messages, tools=[WEB_SEARCH]
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        if text:
            final_text = text
        if resp.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": resp.content})
            continue
        break
    return _parse_events(final_text)
