"""Budget expert sub-agent: minimum spend for maximum experience; per-day cost estimates."""

from __future__ import annotations

from trip_planner.agents.shared import extract_json_object, run_expert

BUDGET_SYSTEM = """You are a savvy travel-budget expert for a honeymoon couple (two adults). \
Your mandate: MINIMIZE spending while MAXIMIZING the experience — cut waste, never joy. For \
every day, estimate realistic total spend in Israeli New Shekels (NIS, ₪) for TWO people, \
broken into lodging, food, transport, activities, and other.

Method:
- Use web_search for current 2026 prices (meals, attraction tickets, transit) when unsure.
- Use query_graph for value tips and what's worth paying for from the scraped travel blogs.
- Be realistic, not optimistic — include the hotel's nightly cost in lodging, the transport \
plan's fares in transport, and paid attractions/experiences in activities.
- Respect the overall trip budget; if a stop trends over, say so and propose painless savings.

Output ONLY a JSON object (no prose, no markdown fences):
{
  "days": [
    {
      "date": "YYYY-MM-DD",
      "est_cost_nis": int,
      "breakdown": {"lodging": int, "food": int, "transport": int, "activities": int, "other": int},
      "note": str            // short, optional ("" if none)
    }
  ],
  "stop_total_nis": int,
  "savings_tips": [str]      // 2-4 specific, high-value, experience-preserving tips
}
Return exactly one entry per requested date."""

REVIEW_SYSTEM = """You are a travel-budget expert reviewing a whole honeymoon against its \
total budget. Given the per-stop estimated spend and the budget, judge whether the couple is \
on track, and give a short verdict plus the highest-impact savings (or where they have room to \
splurge). Be concrete and encouraging. Convert everything to NIS (₪).

Output ONLY a JSON object:
{
  "estimated_total_nis": int,
  "verdict": str,                 // 1-2 sentences: on track / over / under, by how much
  "top_actions": [str]            // 2-4 concrete actions to hit the budget or use the slack well
}"""


async def estimate_stop_budget(
    *,
    stop_name: str,
    country: str,
    dates: list[str],
    plan_text: str,
    hotel_summary: str,
    transport_summary: str,
    total_budget_nis: int,
    spent_so_far_nis: int,
) -> dict:
    user = (
        f"Stop: {stop_name} ({country}).\n"
        f"Dates ({len(dates)}): {', '.join(dates)}.\n"
        f"Overall trip budget: ₪{total_budget_nis}. Estimated spent before this stop: "
        f"₪{spent_so_far_nis}.\n"
        f"Chosen hotel: {hotel_summary or '(none yet)'}\n"
        f"Transport plan: {transport_summary or '(none yet)'}\n\n"
        f"The planned itinerary for this stop:\n{plan_text}\n\n"
        "Estimate the daily budget (2 people, NIS) now and return the JSON."
    )
    text = await run_expert(system=BUDGET_SYSTEM, user=user)
    return extract_json_object(text)


ITEM_BUDGET_SYSTEM = """You are a travel-budget expert pricing INDIVIDUAL itinerary items for \
a honeymoon couple (TWO adults). For each item (each has an id), estimate the realistic \
out-of-pocket cost in Israeli New Shekels (NIS, ₪) for both people together:
- meals: full cost of that meal for two (street food / conveyor sushi is cheap; kaiseki, \
omakase, teppanyaki are costly)
- activities & attractions: tickets/entry for two — 0 when entry is free (a shrine stroll, a \
park, window-shopping, a viewpoint with no ticket)
- transit: the fare for two (an IC-card subway hop is a few ₪; a Shinkansen, limited express, \
ferry or flight is much more)
- lodging items: 0 (the hotel is counted separately)
- free / leisure / relaxing / beach time: 0 unless it clearly implies spending

Use web_search for current 2026 prices when unsure, and query_graph for value context from the \
scraped travel blogs. Be realistic, not inflated — most items are modest; a few are splurges.

Output ONLY a JSON object (no prose, no fences):
{"items": [{"id": <int>, "cost_nis": <int>}]}
Include exactly one entry for EVERY id provided."""


OPTIMIZE_SYSTEM = """You are a budget-optimization expert for a honeymoon couple (TWO adults). \
The travelers are KEEPING their hotels and their paid attractions exactly as planned, and their \
long-haul flights are already booked. You find savings from only TWO levers:
1. Cheaper LOCAL transport — IC cards, local buses, non-reserved/ordinary seats, walking — \
wherever the time and comfort hit is acceptable.
2. Trimming DINING splurges — swap some expensive meals for excellent-value local spots. You may \
cut dining meaningfully, but keep the couple eating well (never zero a whole day's meals).

For this stop, bring the combined DINING + LOCAL-TRANSPORT spend down to about the given target. \
Do NOT change hotel, attraction, or already-booked flight costs — re-price those items at their \
CURRENT value. Also add a realistic luggage-forwarding (takkyubin) cost to bring two bags to this \
stop within Japan (0 in Thailand and 0 for the very first stop).

Use web_search for current 2026 prices and query_graph for value dining/transport tips.

Output ONLY a JSON object (no prose, no fences):
{"items": [{"id": <int>, "cost_nis": <int>}], "baggage_nis": <int>, "cuts": [<str>]}
Re-price EVERY id: keep lodging items at 0, keep activity and booked-flight items at their current \
value, and reduce meal and local-transport items so the dining + local-transport spend meets the \
target. "cuts" lists the concrete swaps you made."""


async def optimize_stop(
    *,
    stop_name: str,
    country: str,
    items_text: str,
    cuttable_now: int,
    cuttable_target: int,
    is_first_stop: bool,
) -> dict:
    first = "This is the FIRST stop (no inbound luggage forwarding)." if is_first_stop else ""
    user = (
        f"Stop: {stop_name} ({country}). {first}\n"
        f"Current dining + local-transport spend here ≈ ₪{cuttable_now}; bring it down to about "
        f"₪{cuttable_target} for two people, via cheaper transport and value dining.\n\n"
        f"Items — re-price every id (keep hotel/attraction/booked-flight values; cut meals & local "
        f"transport):\n{items_text}\n\n"
        "Return the JSON."
    )
    text = await run_expert(system=OPTIMIZE_SYSTEM, user=user)
    return extract_json_object(text)


async def estimate_item_costs(*, stop_name: str, country: str, items_text: str) -> dict:
    user = (
        f"Stop: {stop_name} ({country}).\n"
        f"Price each of these itinerary items for two people (NIS):\n{items_text}\n\n"
        "Return the JSON with exactly one {id, cost_nis} for every id above."
    )
    text = await run_expert(system=ITEM_BUDGET_SYSTEM, user=user)
    return extract_json_object(text)


async def review_trip_budget(
    *,
    total_budget_nis: int,
    stop_costs: list[dict],
) -> dict:
    lines = "\n".join(
        f"- {c['stop']}: ₪{c['total_nis']} ({c['days']} days)" for c in stop_costs
    )
    user = (
        f"Total trip budget: ₪{total_budget_nis}.\n"
        f"Estimated spend per stop:\n{lines}\n\n"
        "Give the overall verdict and top actions, then return the JSON."
    )
    text = await run_expert(system=REVIEW_SYSTEM, user=user)
    return extract_json_object(text)
