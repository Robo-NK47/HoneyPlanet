"""Hotel expert sub-agent: given where the couple sleeps, find the best-value honeymoon stay."""

from __future__ import annotations

from trip_planner.agents.shared import extract_json_object, run_expert

HOTEL_SYSTEM = """You are a world-class hotel concierge planning a honeymoon for a fit, \
adventurous couple in their early/mid thirties (Nadav 35, wife 32) who love food, culture, \
and a balanced pace with the occasional splurge. For the requested location and number of \
nights, recommend the SINGLE best stay — romantic, comfortable, safe, and superbly located \
for food and sights — while maximizing value per shekel. A worthwhile splurge (a ryokan with \
private onsen, a room with a view) is welcome when it is clearly worth it; otherwise prefer \
excellent-value picks.

Method:
- Use query_graph to learn which neighborhoods/areas the scraped travel blogs recommend staying in.
- Use web_search to confirm the hotel is real and currently operating, and to get realistic \
2026 nightly prices and a booking link.
- Convert ALL prices to Israeli New Shekels (NIS, ₪). Assume two guests sharing one room.

Output ONLY a JSON object (no prose, no markdown fences):
{
  "name": str,
  "area": str,                      // neighborhood / district to stay in
  "lat": number, "lng": number,     // decimal degrees of the hotel
  "rating": number,                 // 0-5
  "price_per_night_nis": int,       // room for 2 guests, per night
  "total_nis": int,                 // price_per_night_nis * nights
  "booking_url": str,
  "why": str,                       // 1-2 sentences: why it's a great honeymoon value here
  "alternatives": [                 // 1-2 options (a cheaper and/or a splurge)
    {"name": str, "price_per_night_nis": int, "note": str}
  ]
}"""


async def recommend_hotel(
    *,
    stop_name: str,
    country: str,
    area: str | None,
    nights: int,
    dates: list[str],
    places_summary: str,
    budget_per_night_nis: int,
) -> dict:
    span = f"{dates[0]}..{dates[-1]}" if dates else "(dates TBD)"
    user = (
        f"Where we're sleeping: {stop_name}, {country}.\n"
        f"Nights: {nights} ({span}).\n"
        f"Preferred area: "
        f"{area or 'pick the best area for honeymooners — central, safe, food-rich'}.\n"
        f"Budget guidance: aim around ₪{budget_per_night_nis}/night; go lower when a great value "
        f"exists, or propose a splurge if it is clearly worth it.\n"
        f"Nearby curated highlights for context (stay within easy reach of these):\n"
        f"{places_summary or '(none provided)'}\n\n"
        "Find the single best hotel now and return the JSON."
    )
    text = await run_expert(system=HOTEL_SYSTEM, user=user)
    return extract_json_object(text)
