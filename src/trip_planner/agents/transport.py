"""Transport expert sub-agent: master inter-city legs and getting around, time- & cost-efficient."""

from __future__ import annotations

from trip_planner.agents.shared import extract_json_object, run_expert

TRANSPORT_SYSTEM = """You are a transportation expert for Japan and Thailand. You master both \
(a) the inter-city leg to REACH a destination and (b) GETTING AROUND within it, always \
optimizing for time AND budget. The trip planner depends on your durations being precise and \
realistic — give door-to-door minutes it can build a day around, not optimistic best cases.

Method:
- Use web_search for current 2026 train/bus/flight/ferry schedules and fares, and for whether \
a rail pass (e.g. JR Pass, regional passes, Suica/PASMO/Rabbit card) is worth it for this leg.
- Use query_graph for route and getting-around tips from the scraped travel blogs.
- Convert ALL fares to Israeli New Shekels (NIS, ₪), for two people unless noted.

Output ONLY a JSON object (no prose, no markdown fences):
{
  "arrival_leg": {
    "from": str, "to": str,
    "mode": str,                 // e.g. "Shinkansen Hikari", "Limited Express", "flight", "ferry"
    "duration_min": int,         // realistic door-to-door minutes
    "cost_nis": int,             // 2 people
    "depart_suggestion": str,    // "HH:MM" a sensible departure time
    "booking_notice": str        // what to reserve/buy ahead (or "" if none)
  },
  "getting_around": {
    "summary": str,              // 1-2 sentences on how to move around here
    "recommended_pass": str,     // e.g. "Suica IC card", "no pass needed", "7-day JR Pass"
    "pass_cost_nis": int,        // 0 if none
    "typical_legs": [            // 3-5 common hops between this place's key areas
      {"from": str, "to": str, "mode": str, "minutes": int, "cost_nis": int}
    ]
  }
}"""


async def plan_transport(
    *,
    to_stop: str,
    country: str,
    dates: list[str],
    arrive_from: str,
    intra_areas: str,
) -> dict:
    span = f"{dates[0]}..{dates[-1]}" if dates else "(dates TBD)"
    days = len(dates)
    user = (
        f"Destination stop: {to_stop} ({country}), {span} ({days} days).\n"
        f"Arriving from: {arrive_from}.\n"
        f"Key areas / spots the couple will move between here: "
        f"{intra_areas or '(typical highlights)'}.\n\n"
        "Give the arrival leg (precise door-to-door time and cost) and the getting-around plan, "
        "then return the JSON."
    )
    text = await run_expert(system=TRANSPORT_SYSTEM, user=user)
    return extract_json_object(text)
