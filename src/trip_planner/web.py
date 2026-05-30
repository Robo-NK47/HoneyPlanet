"""Read-only HTML rendering of the trip plan — an interim viewer until the Phase-5 PWA."""

from __future__ import annotations

import html

from trip_planner.models import Trip

KIND_ICON = {"meal": "🍜", "activity": "📍", "transit": "🚆", "lodging": "🏨", "free": "🌿"}
FLAG = {"jp": "🇯🇵", "th": "🇹🇭"}

_CSS = """
:root { color-scheme: dark; }
body {
  font-family: -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 0; background: #0f1115; color: #e8eaed;
}
.wrap { max-width: 820px; margin: 0 auto; padding: 20px; }
h1 { margin: .2em 0; }
.dates { color: #9aa0a6; margin: .2em 0 1em; }
.notes {
  background: #1b2430; border-left: 3px solid #4c8bf5;
  padding: 10px 12px; border-radius: 6px; color: #cfd4da;
}
h2 { margin-top: 1.4em; border-bottom: 1px solid #2a2e35; padding-bottom: .2em; }
ol.route { list-style: none; padding: 0; }
ol.route li {
  padding: 10px 0; border-bottom: 1px solid #20242b;
  display: flex; flex-direction: column; gap: 2px;
}
.city { font-weight: 600; font-size: 1.05em; }
.meta { color: #9aa0a6; font-size: .85em; }
.note { color: #aeb4ba; font-size: .9em; }
h3 { margin: 1.1em 0 .3em; color: #8ab4f8; }
.day { margin: .4em 0; padding: .5em .7em; background: #161a20; border-radius: 8px; }
.dhead { font-weight: 600; margin-bottom: .3em; }
ul.items { list-style: none; margin: 0; padding: 0; }
ul.items li { padding: 3px 0; }
.inote { color: #9aa0a6; }
.todo { color: #6b7177; font-style: italic; font-size: .9em; }
b { color: #f5c869; font-variant-numeric: tabular-nums; }
.foot { color: #6b7177; margin-top: 2em; font-size: .85em; }
"""


def _nights(trip: Trip) -> int:
    if trip.start_date and trip.end_date:
        return (trip.end_date - trip.start_date).days
    return 0


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style>"
        f'</head><body><div class="wrap">{body}'
        '<p class="foot">Draft · interim viewer · the offline editable app arrives in Phase 5</p>'
        "</div></body></html>"
    )


def render_plan(trip: Trip | None) -> str:
    if trip is None:
        body = "<h1>No plan yet</h1><p>Run <code>python scripts/seed_plan.py</code> first.</p>"
        return _page("Trip plan", body)

    parts: list[str] = [f"<h1>{html.escape(trip.name)}</h1>"]
    dates = f"{trip.start_date} → {trip.end_date} · {_nights(trip)} nights"
    parts.append(f"<p class='dates'>{dates}</p>")
    if trip.notes:
        parts.append(f"<p class='notes'>{html.escape(trip.notes)}</p>")

    parts.append("<h2>Route</h2><ol class='route'>")
    for st in trip.stops:
        flag = FLAG.get(st.country or "", "")
        meta = f"{st.nights} nights · {st.arrival_date} → {st.departure_date}"
        parts.append(
            f"<li><span class='city'>{flag} {html.escape(st.name)}</span>"
            f"<span class='meta'>{meta}</span>"
            f"<span class='note'>{html.escape(st.notes or '')}</span></li>"
        )
    parts.append("</ol>")

    parts.append("<h2>Daily plan</h2>")
    for st in trip.stops:
        parts.append(f"<h3>{FLAG.get(st.country or '', '')} {html.escape(st.name)}</h3>")
        for day in st.days:
            head = f"{day.date} — {html.escape(day.title or '')}"
            parts.append(f"<div class='day'><div class='dhead'>{head}</div>")
            if day.items:
                parts.append("<ul class='items'>")
                for it in day.items:
                    icon = KIND_ICON.get(it.kind.value, "•")
                    tm = it.start_time.strftime("%H:%M") if it.start_time else ""
                    note = ""
                    if it.notes:
                        note = f" <span class='inote'>— {html.escape(it.notes)}</span>"
                    parts.append(f"<li>{icon} <b>{tm}</b> {html.escape(it.title or '')}{note}</li>")
                parts.append("</ul>")
            else:
                parts.append("<div class='todo'>to be planned</div>")
            parts.append("</div>")

    return _page(trip.name, "\n".join(parts))
