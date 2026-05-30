"""Plan verifier backed by Claude (Opus 4.8): reviews a stop's itinerary for feasibility."""

from __future__ import annotations

from typing import Literal

import anthropic
from pydantic import BaseModel

MODEL = "claude-opus-4-8"


class Problem(BaseModel):
    day_date: str  # YYYY-MM-DD the problem applies to (or the stop generally)
    severity: Literal["low", "medium", "high"]
    issue: str
    fix: str  # specific, actionable instruction for the planner


class VerifyResult(BaseModel):
    ok: bool  # true only when there are no medium/high problems
    summary: str
    problems: list[Problem]


VERIFY_SYSTEM = """You are a meticulous travel-plan reviewer. You are given one stop's \
day-by-day itinerary and must judge whether it actually makes sense on the ground. Check:

- Geography: places visited on the same day should be reasonably close; flag large \
back-and-forth, impossible hops, or an attraction far from the day's other stops.
- Time & hours: the order should be sensible; flag implausible times or venues likely to be \
closed at the listed time (e.g. a market in late evening, a temple at midnight).
- Pace: flag over-packed days (too many anchors, no room to breathe) and under-filled days \
(no meals, nothing to do). The couple wants a balanced, food-first pace.
- Meals: every day should include proper meals (not just snacks).
- Transit: any move between cities or distant areas needs a transit item with a realistic \
duration; the arrival day and the onward/departure day should have their travel legs.
- Reservations: high-demand venues (fine dining, ryokan, teamLab, theme parks) and ticketed \
transport (Shinkansen, limited expresses, internal flights, ferries) should carry a booking \
note; flag missing ones.

Be specific and practical. Set ok=true ONLY if there are no medium or high severity problems. \
For each problem, write a concrete fix the planner can act on."""


def verify_stop(
    client: anthropic.Anthropic,
    *,
    stop_name: str,
    country: str,
    plan_text: str,
) -> VerifyResult:
    user = (
        f"Review this {country} stop plan for {stop_name}. Identify problems and concrete "
        f"fixes.\n\n{plan_text}"
    )
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4000,
        system=[{"type": "text", "text": VERIFY_SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": user}],
        output_format=VerifyResult,
    )
    return response.parsed_output
