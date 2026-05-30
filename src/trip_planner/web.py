"""HTML rendering of the trip plan: MapLibre map, chat, and a task board. Interim until PWA."""

from __future__ import annotations

import html
import json

from trip_planner.models import Place, Trip

KIND_ICON = {"meal": "🍜", "activity": "📍", "transit": "🚆", "lodging": "🏨", "free": "🌿"}
FLAG = {"jp": "🇯🇵", "th": "🇹🇭"}
CAT_LABEL = {
    "restaurant": "🍽 Eat",
    "attraction": "📸 See",
    "theme_park": "🎢 Parks",
    "food_market": "🛒 Markets",
}
CAT_ORDER = ["restaurant", "attraction", "theme_park", "food_market"]

_CSS = """
:root { color-scheme: dark; }
body {
  font-family: -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 0; background: #0f1115; color: #e8eaed;
}
.wrap { max-width: 1600px; margin: 0 auto; padding: 20px; }
.layout { display: flex; gap: 16px; align-items: flex-start; }
.content { flex: 1 1 38%; min-width: 0; }
.mapcol { flex: 1 1 34%; position: sticky; top: 16px; }
.taskcol { flex: 1 1 28%; position: sticky; top: 16px; }
#map { width: 100%; height: calc(100vh - 290px); border-radius: 10px; background: #1b2430; }
#chat {
  height: 260px; margin-top: 10px; display: flex; flex-direction: column;
  background: #161a20; border-radius: 10px; padding: 8px;
}
#chatlog { flex: 1; overflow-y: auto; font-size: .85em; }
#chatlog .msg { padding: 5px 8px; margin: 4px 0; border-radius: 8px; white-space: pre-wrap; }
#chatlog .user { background: #243044; }
#chatlog .bot { background: #20262e; color: #cdd2d8; }
#chatform { display: flex; gap: 6px; margin-top: 6px; }
#chatinput {
  flex: 1; background: #0f1115; border: 1px solid #2a2e35; color: #e8eaed;
  border-radius: 6px; padding: 6px 8px;
}
#chatform button {
  background: #4c8bf5; color: #fff; border: none; border-radius: 6px;
  padding: 6px 12px; cursor: pointer;
}
#taskboard {
  height: calc(100vh - 32px); overflow-y: auto;
  background: #161a20; border-radius: 10px; padding: 10px;
}
#taskboard h3 { margin: .2em 0 .6em; color: #8ab4f8; }
#taskform { display: flex; flex-direction: column; gap: 6px; margin-bottom: 10px; }
#taskform input, #taskform select {
  background: #0f1115; border: 1px solid #2a2e35; color: #e8eaed;
  border-radius: 6px; padding: 6px 8px;
}
.taskrow2 { display: flex; gap: 6px; }
.taskrow2 input { flex: 1; min-width: 0; }
#taskform button {
  background: #4c8bf5; color: #fff; border: none;
  border-radius: 6px; padding: 6px 12px; cursor: pointer;
}
.taskdate {
  color: #9aa0a6; font-size: .8em; margin: 12px 0 3px;
  border-bottom: 1px solid #20242b; padding-bottom: 2px;
}
.task {
  display: flex; align-items: center; gap: 7px;
  padding: 5px 2px; border-bottom: 1px solid #181c22; font-size: .9em;
}
.task.done .ttitle { text-decoration: line-through; color: #6b7177; }
.task .ttitle { flex: 1; cursor: pointer; }
.task .timp {
  width: 16px; min-width: 16px; height: 16px; border-radius: 4px; color: #111;
  font-size: .7em; font-weight: 700; text-align: center; line-height: 16px; cursor: pointer;
}
.task .tdel { background: none; border: none; color: #6b7177; cursor: pointer; font-size: 1.1em; }
.task .tdel:hover { color: #e05260; }
@media (max-width: 1100px) {
  .layout { flex-direction: column; }
  .mapcol, .taskcol { position: static; width: 100%; }
  #map { height: 55vh; }
  #taskboard { height: auto; max-height: 60vh; }
}
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
.picks { margin: .2em 0 .6em; font-size: .9em; }
.pickrow { padding: 2px 0; color: #c2c7cd; }
.catlabel { color: #8ab4f8; font-weight: 600; margin-right: 4px; }
.picks a {
  color: #e8eaed; text-decoration: none;
  border-bottom: 1px dotted #4c8bf5; cursor: pointer;
}
.picks a:hover { color: #fff; background: #243044; }
.star { color: #f5c869; font-size: .85em; margin: 0 6px 0 2px; }
.day {
  margin: .4em 0; padding: .5em .7em; background: #161a20; border-radius: 8px;
  border-left: 2px solid transparent;
}
.day[data-mids]:hover { border-left-color: #4c8bf5; background: #1a2029; }
.dhead { font-weight: 600; margin-bottom: .3em; }
ul.items { list-style: none; margin: 0; padding: 0; }
ul.items li { padding: 3px 0; }
ul.items li[data-mid] { cursor: pointer; }
.inote { color: #9aa0a6; }
.book {
  color: #ffcf8a; background: #2a2410; padding: 2px 7px;
  border-radius: 5px; font-size: .82em; margin: 3px 0 2px 18px;
}
.todo { color: #6b7177; font-style: italic; font-size: .9em; }
b { color: #f5c869; font-variant-numeric: tabular-nums; }
.foot { color: #6b7177; margin-top: 2em; font-size: .85em; }
"""

_MAP_JS = """
const COLORS = ['match', ['get', 'cat'],
  'restaurant', '#e74c3c', 'attraction', '#4c8bf5',
  'theme_park', '#9b59b6', 'food_market', '#2ecc71', '#888'];
const map = new maplibregl.Map({
  container: 'map',
  style: 'https://tiles.openfreemap.org/styles/liberty',
  center: [138.0, 36.0], zoom: 4
});
map.addControl(new maplibregl.NavigationControl({showCompass: false}));
function escapeHtml(s) {
  const d = document.createElement('div'); d.textContent = s; return d.innerHTML;
}
function boundsOf(ids) {
  const b = new maplibregl.LngLatBounds(); let any = false;
  ids.forEach(function(id) {
    const m = MARKERS[id]; if (m) { b.extend([m.lng, m.lat]); any = true; }
  });
  return any ? b : null;
}
let HL = [];
function clearHL() {
  HL.forEach(function(id) { map.setFeatureState({source: 'places', id: id}, {hl: false}); });
  HL = [];
}
function setHL(ids) {
  clearHL();
  ids.forEach(function(id) { map.setFeatureState({source: 'places', id: id}, {hl: true}); });
  HL = ids.slice();
  const b = boundsOf(ids); if (b) map.fitBounds(b, {padding: 60, maxZoom: 14});
}
function wireHover() {
  document.querySelectorAll('[data-mid]').forEach(function(el) {
    el.addEventListener('mouseenter', function() {
      const id = Number(el.dataset.mid); const m = MARKERS[id];
      if (m) { setHL([id]); map.flyTo({center: [m.lng, m.lat], zoom: 14}); }
    });
  });
  document.querySelectorAll('[data-mids]').forEach(function(el) {
    const ids = el.dataset.mids.split(',').filter(Boolean).map(Number);
    el.addEventListener('mouseenter', function() { if (ids.length) setHL(ids); });
    el.addEventListener('mouseleave', clearHL);
  });
}
map.on('load', function() {
  try {
    (map.getStyle().layers || []).forEach(function(ly) {
      if (ly.type === 'symbol' && ly.layout && ly.layout['text-field'] !== undefined) {
        map.setLayoutProperty(ly.id, 'text-field',
          ['coalesce', ['get', 'name:en'], ['get', 'name:latin'], ['get', 'name']]);
      }
    });
  } catch (e) {}
  const feats = Object.keys(MARKERS).map(function(id) {
    const m = MARKERS[id];
    return {type: 'Feature', id: Number(id),
      geometry: {type: 'Point', coordinates: [m.lng, m.lat]},
      properties: {cat: m.cat, name: m.name, url: m.url, rating: m.rating}};
  });
  map.addSource('places', {type: 'geojson', data: {type: 'FeatureCollection', features: feats}});
  map.addLayer({id: 'places', type: 'circle', source: 'places', paint: {
    'circle-radius': ['case', ['boolean', ['feature-state', 'hl'], false], 9, 6],
    'circle-color': COLORS,
    'circle-stroke-color': '#fff',
    'circle-stroke-width': ['case', ['boolean', ['feature-state', 'hl'], false], 3, 1.4]
  }});
  const b = boundsOf(Object.keys(MARKERS).map(Number));
  if (b) map.fitBounds(b, {padding: 40, maxZoom: 12});
  map.on('click', 'places', function(e) {
    const f = e.features[0]; const p = f.properties;
    let h = '<b>' + escapeHtml(p.name) + '</b>' + (p.rating ? (' ★' + p.rating) : '');
    if (p.url && p.url !== '#') {
      h += '<br><a href="' + p.url + '" target="_blank" rel="noopener">website ↗</a>';
    }
    new maplibregl.Popup().setLngLat(f.geometry.coordinates.slice()).setHTML(h).addTo(map);
  });
  map.on('mouseenter', 'places', function() { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'places', function() { map.getCanvas().style.cursor = ''; });
  wireHover();
});
"""

_TASK_JS = """
const tasklist = document.getElementById('tasklist');
const taskform = document.getElementById('taskform');
const IMPCOL = {high: '#e05260', medium: '#e0a23e', low: '#5aa9a0'};
async function loadTasks() {
  const r = await fetch('/tasks');
  renderTasks(await r.json());
}
function renderTasks(tasks) {
  tasklist.innerHTML = '';
  const groups = {};
  tasks.forEach(function(t) {
    const k = t.due_date || 'No date';
    (groups[k] = groups[k] || []).push(t);
  });
  Object.keys(groups).sort().forEach(function(k) {
    const h = document.createElement('div'); h.className = 'taskdate'; h.textContent = k;
    tasklist.appendChild(h);
    groups[k].forEach(function(t) { tasklist.appendChild(taskEl(t)); });
  });
}
function taskEl(t) {
  const row = document.createElement('div');
  row.className = 'task' + (t.done ? ' done' : '');
  const cb = document.createElement('input'); cb.type = 'checkbox'; cb.checked = t.done;
  cb.addEventListener('change', function() { patchTask(t.id, {done: cb.checked}); });
  const imp = document.createElement('span'); imp.className = 'timp';
  imp.textContent = t.importance[0].toUpperCase();
  imp.style.background = IMPCOL[t.importance] || '#666';
  imp.title = 'click to change importance';
  imp.addEventListener('click', function() {
    const order = ['low', 'medium', 'high'];
    patchTask(t.id, {importance: order[(order.indexOf(t.importance) + 1) % 3]});
  });
  const title = document.createElement('span'); title.className = 'ttitle';
  title.textContent = t.title; title.title = 'click to rename';
  title.addEventListener('click', function() {
    const v = prompt('Edit task', t.title); if (v) patchTask(t.id, {title: v});
  });
  const del = document.createElement('button'); del.className = 'tdel'; del.textContent = '\\u00d7';
  del.addEventListener('click', function() { delTask(t.id); });
  row.append(cb, imp, title, del);
  return row;
}
async function patchTask(id, data) {
  await fetch('/tasks/' + id, {
    method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)
  });
  loadTasks();
}
async function delTask(id) {
  await fetch('/tasks/' + id, {method: 'DELETE'});
  loadTasks();
}
taskform.addEventListener('submit', async function(e) {
  e.preventDefault();
  const title = document.getElementById('tasktitle').value.trim(); if (!title) return;
  const due = document.getElementById('taskdate').value || null;
  const imp = document.getElementById('taskimp').value;
  await fetch('/tasks', {
    method: 'POST', headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({title: title, due_date: due, importance: imp})
  });
  document.getElementById('tasktitle').value = '';
  loadTasks();
});
loadTasks();
"""

_CHAT_JS = """
const chatlog = document.getElementById('chatlog');
const chatform = document.getElementById('chatform');
const chatinput = document.getElementById('chatinput');
let chatHistory = [];
function addMsg(role, text) {
  const d = document.createElement('div');
  d.className = 'msg ' + role; d.textContent = text;
  chatlog.appendChild(d); chatlog.scrollTop = chatlog.scrollHeight;
  return d;
}
addMsg('bot', 'Hi! Ask about the plan, edit it, manage tasks, or search the web.');
chatform.addEventListener('submit', async function(e) {
  e.preventDefault();
  const msg = chatinput.value.trim(); if (!msg) return;
  addMsg('user', msg); chatinput.value = '';
  const pending = addMsg('bot', '…');
  try {
    const r = await fetch('/chat', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message: msg, history: chatHistory})
    });
    const data = await r.json();
    pending.textContent = data.reply;
    chatHistory = data.history;
    if (data.tasks_changed && typeof loadTasks === 'function') { loadTasks(); }
    if (data.changed) {
      addMsg('bot', '(plan updated — refreshing…)');
      setTimeout(function() { location.reload(); }, 1200);
    }
  } catch (err) {
    pending.textContent = 'Error: ' + err;
  }
});
"""


def _nights(trip: Trip) -> int:
    if trip.start_date and trip.end_date:
        return (trip.end_date - trip.start_date).days
    return 0


def _map_script(markers: list[dict]) -> str:
    data = {
        str(m["id"]): {
            "lat": m["lat"],
            "lng": m["lng"],
            "name": m["name"],
            "cat": m["cat"],
            "url": m["url"],
            "rating": m["rating"],
        }
        for m in markers
    }
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"<script>const MARKERS = {blob};{_MAP_JS}</script>"


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>'
        '<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style>"
        f'</head><body><div class="wrap">{body}'
        '<p class="foot">Draft · interim viewer · the offline editable app arrives in Phase 5</p>'
        "</div></body></html>"
    )


def _picks_html(places: list[Place]) -> str:
    by_cat: dict[str, list[Place]] = {}
    for p in places:
        cat = (p.tags or {}).get("category") or p.subtype or "other"
        by_cat.setdefault(cat, []).append(p)

    rows: list[str] = []
    for cat in CAT_ORDER:
        items = by_cat.get(cat)
        if not items:
            continue
        items.sort(key=lambda x: (x.tags or {}).get("rank", 99))
        links: list[str] = []
        for p in items:
            url = (p.tags or {}).get("website") or (p.tags or {}).get("maps_uri") or "#"
            star = f"★{p.rating}" if p.rating else ""
            links.append(
                f"<a href='{html.escape(url)}' target='_blank' rel='noopener' "
                f"data-mid='{p.id}'>{html.escape(p.name)}</a><span class='star'>{star}</span>"
            )
        label = CAT_LABEL.get(cat, cat)
        joined = " · ".join(links)
        rows.append(f"<div class='pickrow'><span class='catlabel'>{label}</span> {joined}</div>")
    return f"<div class='picks'>{''.join(rows)}</div>" if rows else ""


def _content_html(trip: Trip, places_by_stop: dict[int, list[Place]]) -> str:
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
        picks = _picks_html(places_by_stop.get(st.id, []))
        if picks:
            parts.append(picks)
        for day in st.days:
            head = f"{day.date} — {html.escape(day.title or '')}"
            mids = ",".join(str(it.place_id) for it in day.items if it.place_id)
            mids_attr = f" data-mids='{mids}'" if mids else ""
            parts.append(f"<div class='day'{mids_attr}><div class='dhead'>{head}</div>")
            if day.items:
                parts.append("<ul class='items'>")
                for it in day.items:
                    icon = KIND_ICON.get(it.kind.value, "•")
                    tm = it.start_time.strftime("%H:%M") if it.start_time else ""
                    mid = f" data-mid='{it.place_id}'" if it.place_id else ""
                    note = ""
                    if it.notes:
                        note = f" <span class='inote'>— {html.escape(it.notes)}</span>"
                    booking = ""
                    if it.booking_notice:
                        booking = f"<div class='book'>📌 {html.escape(it.booking_notice)}</div>"
                    parts.append(
                        f"<li{mid}>{icon} <b>{tm}</b> "
                        f"{html.escape(it.title or '')}{note}{booking}</li>"
                    )
                parts.append("</ul>")
            else:
                parts.append("<div class='todo'>to be planned</div>")
            parts.append("</div>")
    return "\n".join(parts)


_TASKBOARD_HTML = (
    '<div class="taskcol"><div id="taskboard"><h3>Tasks</h3>'
    '<form id="taskform"><input id="tasktitle" autocomplete="off" '
    'placeholder="New task… e.g. Book Gora Kadan ryokan"/>'
    '<div class="taskrow2"><input id="taskdate" type="date"/>'
    '<select id="taskimp"><option value="high">High</option>'
    '<option value="medium" selected>Med</option>'
    '<option value="low">Low</option></select>'
    "<button>Add</button></div></form><div id=\"tasklist\"></div></div></div>"
)


def render_plan(
    trip: Trip | None,
    places_by_stop: dict[int, list[Place]] | None = None,
    markers: list[dict] | None = None,
) -> str:
    if trip is None:
        body = "<h1>No plan yet</h1><p>Run <code>python scripts/seed_plan.py</code> first.</p>"
        return _page("Trip plan", body)

    content = _content_html(trip, places_by_stop or {})
    body = (
        '<div class="layout">'
        f'<div class="content">{content}</div>'
        '<div class="mapcol"><div id="map"></div>'
        '<div id="chat"><div id="chatlog"></div>'
        '<form id="chatform"><input id="chatinput" autocomplete="off" '
        'placeholder="Ask, edit the plan, or manage tasks…"/>'
        "<button>Send</button></form></div></div>"
        f"{_TASKBOARD_HTML}"
        "</div>"
        f"{_map_script(markers or [])}"
        f"<script>{_TASK_JS}</script>"
        f"<script>{_CHAT_JS}</script>"
    )
    return _page(trip.name, body)
