"""HTML rendering of the trip plan: MapLibre map, chat, task board, and events."""

from __future__ import annotations

import html
import json
from urllib.parse import quote_plus

from trip_planner.models import Place, Trip

KIND_ICON = {"meal": "🍜", "activity": "📍", "transit": "🚆", "lodging": "🏨", "free": "🌿"}
INTL_FLIGHT = "international-flight"  # transit_mode sentinel: shown in the Flights section
FLAG = {"jp": "🇯🇵", "th": "🇹🇭"}
CAT_LABEL = {
    "restaurant": "🍽 Eat",
    "attraction": "📸 See",
    "theme_park": "🎢 Parks",
    "food_market": "🛒 Markets",
}
CAT_ORDER = ["restaurant", "attraction", "theme_park", "food_market"]
EVT_ICON = {
    "festival": "🎌",
    "seasonal": "🍁",
    "illumination": "✨",
    "market": "🏮",
    "cultural": "🎎",
}

def _safe_url(url: str | None) -> str:
    """Allow only http(s)/mailto links (then HTML-escape). Blocks javascript:/data: URLs that
    can arrive from scraped place/event/hotel data."""
    url = (url or "").strip()
    if url.lower().startswith(("http://", "https://", "mailto:")):
        return html.escape(url, quote=True)
    return "#"


_CSS = """
:root { color-scheme: dark; }
body {
  font-family: -apple-system, Segoe UI, Roboto, sans-serif;
  margin: 0; background: #0f1115; color: #e8eaed;
}
.wrap { max-width: 1600px; margin: 0 auto; padding: 20px; }
.layout { display: flex; gap: 16px; align-items: flex-start; }
.content { flex: 1 1 38%; min-width: 0; }
.mapcol {
  flex: 1 1 34%; position: sticky; top: 16px;
  height: calc(100vh - 32px); display: flex; flex-direction: column;
}
.taskcol { flex: 1 1 28%; position: sticky; top: 16px; }
#map { width: 100%; flex: 1; min-height: 0; border-radius: 10px; background: #1b2430; }
#chat {
  flex: none; height: 260px; margin-top: 10px; display: flex; flex-direction: column;
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
  .mapcol, .taskcol { position: static; width: 100%; height: auto; display: block; }
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
.events { margin: .3em 0; }
.events .erow { padding: 3px 0; color: #cfd4da; font-size: .9em; }
.events .edate { color: #9aa0a6; font-size: .85em; }
.events .ecat { display: inline-block; width: 16px; text-align: center; margin-right: 4px; }
details.sec { margin: 1.4em 0 0; }
summary.sechead {
  font-size: 1.3em; font-weight: 600; cursor: pointer; list-style: none;
  border-bottom: 1px solid #2a2e35; padding-bottom: .2em; margin-bottom: .5em;
  display: flex; align-items: center; gap: .45em; color: #e8eaed;
}
.dayctl { display: flex; gap: 8px; margin: 0 0 .7em; }
.dayctl button {
  background: #20262e; color: #9aa0a6; border: 1px solid #2a2e35;
  border-radius: 6px; padding: 3px 11px; cursor: pointer; font-size: .82em;
}
.dayctl button:hover { color: #e8eaed; border-color: #4c8bf5; }
.day {
  margin: .4em 0; padding: .35em .7em; background: #161a20; border-radius: 8px;
  border-left: 2px solid transparent;
}
.day[data-mids]:hover { border-left-color: #4c8bf5; background: #1a2029; }
summary.dhead {
  font-weight: 600; cursor: pointer; list-style: none;
  display: flex; align-items: center; gap: .45em; padding: .15em 0;
}
.daybody { padding: .15em 0 .25em; }
.daycount { margin-left: auto; color: #6b7177; font-size: .8em; font-weight: 400; }
.dsum-evt { font-size: .95em; letter-spacing: 1px; }
summary.sechead::-webkit-details-marker,
summary.dhead::-webkit-details-marker { display: none; }
summary.sechead::before, summary.dhead::before {
  content: '\\25b8'; color: #8ab4f8; font-size: .75em;
  transition: transform .15s ease; display: inline-block;
}
details[open] > summary.sechead::before,
details[open] > summary.dhead::before { transform: rotate(90deg); }
.evt {
  display: inline-block; margin: 1px 4px 5px 0; padding: 2px 8px;
  background: #2a2412; color: #f5c869; border: 1px solid #5a4a1e;
  border-radius: 5px; font-size: .82em;
}
.evt a { color: #f5c869; text-decoration: none; }
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
.budget { margin: .7em 0 1.2em; padding: 10px 12px; background: #161a20; border-radius: 8px; }
.budget .bhead {
  display: flex; justify-content: space-between; align-items: baseline;
  font-size: .9em; margin-bottom: 6px;
}
.budget .bnum { color: #f5c869; font-weight: 600; font-variant-numeric: tabular-nums; }
.bbar { height: 8px; background: #2a2e35; border-radius: 4px; overflow: hidden; }
.bbar > span { display: block; height: 100%; background: linear-gradient(90deg, #2ecc71, #4c8bf5); }
.bbar.over > span { background: linear-gradient(90deg, #e0a23e, #e05260); }
.budget .btip { color: #9aa0a6; font-size: .8em; margin-top: 5px; }
.hotel {
  margin: 5px 0 2px; padding: 6px 9px; background: #1a1530;
  border-left: 3px solid #e056fd; border-radius: 6px; font-size: .86em; color: #d8c6f0;
}
.hotel .hname { color: #f0e0ff; font-weight: 600; }
.hotel a { color: #e0a0ff; text-decoration: none; border-bottom: 1px dotted #e056fd; }
.hotel a:hover { color: #fff; }
.hotel .book-btn {
  border-bottom: none; margin-left: 6px; padding: 1px 9px; border-radius: 5px;
  background: #e056fd; color: #fff; font-size: .82em; font-weight: 600; white-space: nowrap;
}
.hotel .book-btn:hover { background: #c93fe0; color: #fff; }
.dcost {
  margin-left: auto; color: #7ad6a0; font-size: .8em; font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.breakdown { color: #8a9aa0; font-size: .8em; margin: 1px 0 5px; }
.icost { color: #7ad6a0; font-size: .82em; font-weight: 600; font-variant-numeric: tabular-nums; }
.icost.free { color: #8a9aa0; font-weight: 400; }
.stoptot { font-size: .7em; font-weight: 600; color: #7ad6a0; font-variant-numeric: tabular-nums; }
.bcountry { display: flex; gap: 16px; margin-top: 7px; font-size: .82em; color: #9aa0a6; }
.bcountry b { color: #f5c869; }
.legend {
  flex: none; display: flex; flex-wrap: wrap; gap: 6px 12px; font-size: .75em;
  color: #9aa0a6; margin: 8px 2px 0;
}
.legend span { display: inline-flex; align-items: center; gap: 4px; }
.legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
"""

_MAP_JS = """
const COLORS = ['match', ['get', 'cat'],
  'restaurant', '#e74c3c', 'attraction', '#4c8bf5',
  'theme_park', '#9b59b6', 'food_market', '#2ecc71', 'hotel', '#e056fd', '#888'];
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
    var pu = (p.url && /^(https?:|mailto:)/i.test(p.url)) ? p.url : '';
    if (pu) {
      h += '<br><a href="' + pu + '" target="_blank" rel="noopener">website ↗</a>';
    }
    new maplibregl.Popup().setLngLat(f.geometry.coordinates.slice()).setHTML(h).addTo(map);
  });
  map.on('mouseenter', 'places', function() { map.getCanvas().style.cursor = 'pointer'; });
  map.on('mouseleave', 'places', function() { map.getCanvas().style.cursor = ''; });
  if (EVENTS && EVENTS.length) {
    const ef = EVENTS.map(function(e) {
      return {type: 'Feature',
        geometry: {type: 'Point', coordinates: [e.lng, e.lat]},
        properties: {name: e.name, dates: e.dates, url: e.url}};
    });
    map.addSource('events', {type: 'geojson', data: {type: 'FeatureCollection', features: ef}});
    map.addLayer({id: 'events', type: 'circle', source: 'events', paint: {
      'circle-radius': 7, 'circle-color': '#f5c869',
      'circle-stroke-color': '#7a5b12', 'circle-stroke-width': 2
    }});
    map.on('click', 'events', function(e) {
      const p = e.features[0].properties;
      let h = '🎌 <b>' + escapeHtml(p.name) + '</b><br>' + escapeHtml(p.dates || '');
      var eu = (p.url && /^(https?:|mailto:)/i.test(p.url)) ? p.url : '';
      if (eu) {
        h += '<br><a href="' + eu + '" target="_blank" rel="noopener">details ↗</a>';
      }
      new maplibregl.Popup().setLngLat(e.features[0].geometry.coordinates.slice())
        .setHTML(h).addTo(map);
    });
    map.on('mouseenter', 'events', function() { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'events', function() { map.getCanvas().style.cursor = ''; });
  }
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
  d.className = 'msg ' + role; d.dir = 'auto'; d.textContent = text;
  chatlog.appendChild(d); chatlog.scrollTop = chatlog.scrollHeight;
  return d;
}
addMsg('bot', 'Hi! Ask about the plan, events, edit it, manage tasks, or search the web.');
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

_UI_JS = """
const TPC_KEY = 'tp-collapse';
function tpcLoad() {
  try { return JSON.parse(localStorage.getItem(TPC_KEY) || '{}'); } catch (e) { return {}; }
}
function tpcSave(s) { try { localStorage.setItem(TPC_KEY, JSON.stringify(s)); } catch (e) {} }
(function () {
  const state = tpcLoad();
  document.querySelectorAll('details[data-key]').forEach(function (d) {
    const k = d.dataset.key;
    if (k in state) d.open = state[k];
    d.addEventListener('toggle', function () {
      const s = tpcLoad(); s[k] = d.open; tpcSave(s);
    });
  });
  function setAllDays(open) {
    const s = tpcLoad();
    document.querySelectorAll('details.day').forEach(function (d) {
      d.open = open; if (d.dataset.key) s[d.dataset.key] = open;
    });
    tpcSave(s);
  }
  const ex = document.getElementById('expandAll');
  const co = document.getElementById('collapseAll');
  if (ex) ex.addEventListener('click', function () { setAllDays(true); });
  if (co) co.addEventListener('click', function () { setAllDays(false); });
})();
"""


def _nights(trip: Trip) -> int:
    if trip.start_date and trip.end_date:
        return (trip.end_date - trip.start_date).days
    return 0


def _map_script(markers: list[dict], events: list[dict]) -> str:
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
    ev_blob = json.dumps(events, ensure_ascii=False).replace("</", "<\\/")
    return f"<script>const MARKERS = {blob};const EVENTS = {ev_blob};{_MAP_JS}</script>"


def _page(title: str, body: str) -> str:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<link rel="manifest" href="/manifest.webmanifest">'
        '<meta name="theme-color" content="#0f1115">'
        '<link rel="icon" href="/icon.svg"><link rel="apple-touch-icon" href="/icon.svg">'
        '<link href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css" rel="stylesheet"/>'
        '<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>'
        f"<title>{html.escape(title)}</title><style>{_CSS}</style>"
        f'</head><body><div class="wrap">{body}'
        '<p class="foot">Draft · interim viewer · installable &amp; offline-capable (PWA)</p>'
        "</div>"
        "<script>if('serviceWorker' in navigator){window.addEventListener('load',function(){"
        "navigator.serviceWorker.register('/sw.js').catch(function(){});});}</script>"
        "</body></html>"
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
                f"<a href='{_safe_url(url)}' target='_blank' rel='noopener' "
                f"data-mid='{p.id}'>{html.escape(p.name)}</a><span class='star'>{star}</span>"
            )
        label = CAT_LABEL.get(cat, cat)
        joined = " · ".join(links)
        rows.append(f"<div class='pickrow'><span class='catlabel'>{label}</span> {joined}</div>")
    return f"<div class='picks'>{''.join(rows)}</div>" if rows else ""


def _event_link(ev: dict) -> str:
    name = html.escape(ev["name"])
    if ev.get("url"):
        return f"<a href='{_safe_url(ev['url'])}' target='_blank' rel='noopener'>{name}</a>"
    return name


def _events_overview(all_events: list[dict]) -> str:
    if not all_events:
        return ""
    rows = [
        "<details class='sec' data-key='sec:events'>"
        f"<summary class='sechead'>Festivals &amp; seasonal events "
        f"<span class='daycount'>{len(all_events)}</span></summary>"
        "<div class='secbody'><div class='events'>"
    ]
    for ev in all_events:
        icon = EVT_ICON.get(ev.get("category") or "", "🎉")
        city = html.escape(ev.get("city") or "")
        edate = html.escape(ev["dates"])
        link = _event_link(ev)
        rows.append(
            f"<div class='erow'><span class='ecat'>{icon}</span>"
            f"<span class='edate'>{edate}</span> · {city} — {link}</div>"
        )
    rows.append("</div></div></details>")
    return "".join(rows)


def _budget_banner(budget: dict) -> str:
    total = budget.get("total_est") or 0
    cap = budget.get("budget") or 0
    if not total or not cap:
        return ""
    pct = min(100, round(total / cap * 100))
    over = total > cap
    cls = "bbar over" if over else "bbar"
    tip = f"{round(total / cap * 100)}% of the ₪{cap:,} budget" + (
        " — trending over, trim a little" if over else " — on track"
    )
    bits: list[str] = []
    flights = budget.get("flights_total")
    if flights:
        ground = budget.get("ground") or (total - flights)
        bits.append(f"<span>🏝 On-the-ground <b>₪{ground:,}</b></span>")
        bits.append(f"<span>✈️ Flights <b>₪{flights:,}</b></span>")
    countries = budget.get("by_country") or {}
    for code, label in (("jp", "🇯🇵 Japan"), ("th", "🇹🇭 Thailand")):
        if countries.get(code):
            bits.append(f"<span>{label} <b>₪{countries[code]:,}</b></span>")
    csplit = f"<div class='bcountry'>{''.join(bits)}</div>" if bits else ""
    return (
        "<div class='budget'><div class='bhead'><span>Estimated spend (2 travelers)</span>"
        f"<span class='bnum'>₪{total:,} / ₪{cap:,}</span></div>"
        f"<div class='{cls}'><span style='width:{pct}%'></span></div>"
        f"<div class='btip'>{tip}</div>{csplit}</div>"
    )


def _flights_section(flights: list[dict]) -> str:
    if not flights:
        return ""
    total = sum(f.get("cost") or 0 for f in flights)
    rows = [
        "<details class='sec' data-key='sec:flights'>"
        f"<summary class='sechead'>✈️ Flights <span class='daycount'>₪{total:,}</span></summary>"
        "<div class='secbody'><div class='events'>"
    ]
    for f in flights:
        cost = f.get("cost") or 0
        leg = html.escape(f.get("leg") or "")
        when = html.escape(f.get("date") or "")
        rows.append(
            f"<div class='erow'><span class='ecat'>✈️</span>"
            f"<span class='edate'>{when}</span> {leg} — "
            f"<span class='icost'>₪{cost:,}</span></div>"
        )
    rows.append("</div></div></details>")
    return "".join(rows)


def _hotel_html(hotel: dict | None) -> str:
    if not hotel or not hotel.get("name"):
        return ""
    name = html.escape(hotel["name"])
    url = hotel.get("url") or (
        "https://www.booking.com/searchresults.html?ss=" + quote_plus(hotel["name"])
    )
    safe = _safe_url(url)
    nm = f"<a href='{safe}' target='_blank' rel='noopener'>{name}</a>"
    area = html.escape(hotel.get("area") or "")
    price = ""
    if hotel.get("price_per_night_nis"):
        price = f" · ₪{hotel['price_per_night_nis']:,}/night"
    book = f"<a class='book-btn' href='{safe}' target='_blank' rel='noopener'>Book ↗</a>"
    why = f"<br><span class='note'>{html.escape(hotel['why'])}</span>" if hotel.get("why") else ""
    return (
        f"<div class='hotel'>🏨 <span class='hname'>{nm}</span> {area}{price} {book}{why}</div>"
    )


def _breakdown_html(cb: dict | None) -> str:
    if not cb:
        return ""
    order = ("lodging", "food", "transport", "activities", "other")
    bits = [f"{k} ₪{cb[k]:,}" for k in order if cb.get(k)]
    return f"<div class='breakdown'>{' · '.join(bits)}</div>" if bits else ""


def _content_html(
    trip: Trip,
    places_by_stop: dict[int, list[Place]],
    day_events: dict[int, list[dict]],
    all_events: list[dict],
    hotels_by_stop: dict[int, dict],
    budget: dict,
    flights: list[dict],
) -> str:
    parts: list[str] = [f"<h1>{html.escape(trip.name)}</h1>"]
    dates = f"{trip.start_date} → {trip.end_date} · {_nights(trip)} nights"
    parts.append(f"<p class='dates'>{dates}</p>")
    if trip.notes:
        parts.append(f"<p class='notes'>{html.escape(trip.notes)}</p>")
    parts.append(_budget_banner(budget))
    parts.append(_flights_section(flights))

    parts.append(
        "<details class='sec' open data-key='sec:route'>"
        "<summary class='sechead'>Route</summary><div class='secbody'><ol class='route'>"
    )
    for st in trip.stops:
        flag = FLAG.get(st.country or "", "")
        meta = f"{st.nights} nights · {st.arrival_date} → {st.departure_date}"
        sub = budget.get("by_stop", {}).get(st.id)
        if sub:
            meta += f" · est. ₪{sub:,}"
        parts.append(
            f"<li><span class='city'>{flag} {html.escape(st.name)}</span>"
            f"<span class='meta'>{meta}</span>"
            f"<span class='note'>{html.escape(st.notes or '')}</span>"
            f"{_hotel_html(hotels_by_stop.get(st.id))}</li>"
        )
    parts.append("</ol></div></details>")
    parts.append(_events_overview(all_events))

    parts.append(
        "<details class='sec' open data-key='sec:daily'>"
        "<summary class='sechead'>Daily plan</summary><div class='secbody'>"
        "<div class='dayctl'>"
        "<button type='button' id='expandAll'>Expand all</button>"
        "<button type='button' id='collapseAll'>Collapse all</button></div>"
    )
    for st in trip.stops:
        stot = budget.get("by_stop", {}).get(st.id)
        stot_html = f" <span class='stoptot'>₪{stot:,}</span>" if stot else ""
        parts.append(
            f"<h3>{FLAG.get(st.country or '', '')} {html.escape(st.name)}{stot_html}</h3>"
        )
        picks = _picks_html(places_by_stop.get(st.id, []))
        if picks:
            parts.append(picks)
        for day in st.days:
            head = f"{day.date} — {html.escape(day.title or '')}"
            evs = day_events.get(day.id, [])
            ev_icons = "".join(EVT_ICON.get(e.get("category") or "", "🎉") for e in evs)
            ev_sum = f"<span class='dsum-evt'>{ev_icons}</span>" if ev_icons else ""
            vis = [it for it in day.items if it.transit_mode != INTL_FLIGHT]
            n = len(vis)
            count = (
                f"<span class='daycount'>{n} stop{'s' if n != 1 else ''}</span>"
                if n
                else "<span class='daycount'>to plan</span>"
            )
            cost_html = f"<span class='dcost'>₪{day.est_cost:,}</span>" if day.est_cost else ""
            mids = ",".join(str(it.place_id) for it in vis if it.place_id)
            mids_attr = f" data-mids='{mids}'" if mids else ""
            parts.append(
                f"<details class='day'{mids_attr} data-key='day:{day.date}'>"
                f"<summary class='dhead'>{head}{ev_sum}{cost_html}{count}</summary>"
                "<div class='daybody'>"
            )
            parts.append(_breakdown_html(day.cost_breakdown))
            for ev in evs:
                icon = EVT_ICON.get(ev.get("category") or "", "🎉")
                parts.append(f"<div class='evt'>{icon} {_event_link(ev)}</div>")
            if vis:
                parts.append("<ul class='items'>")
                for it in vis:
                    icon = KIND_ICON.get(it.kind.value, "•")
                    tm = it.start_time.strftime("%H:%M") if it.start_time else ""
                    mid = f" data-mid='{it.place_id}'" if it.place_id else ""
                    note = ""
                    if it.notes:
                        note = f" <span class='inote'>— {html.escape(it.notes)}</span>"
                    booking = ""
                    if it.booking_notice:
                        booking = f"<div class='book'>📌 {html.escape(it.booking_notice)}</div>"
                    icost = ""
                    if it.est_cost:
                        icost = f" <span class='icost'>₪{it.est_cost:,}</span>"
                    elif it.est_cost == 0 and it.kind.value in ("meal", "activity", "transit"):
                        icost = " <span class='icost free'>free</span>"
                    parts.append(
                        f"<li{mid}>{icon} <b>{tm}</b> "
                        f"{html.escape(it.title or '')}{icost}{note}{booking}</li>"
                    )
                parts.append("</ul>")
            else:
                parts.append("<div class='todo'>to be planned</div>")
            parts.append("</div></details>")
    parts.append("</div></details>")
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

_LEGEND = (
    "<div class='legend'>"
    "<span><i style='background:#e74c3c'></i>Eat</span>"
    "<span><i style='background:#4c8bf5'></i>See</span>"
    "<span><i style='background:#9b59b6'></i>Parks</span>"
    "<span><i style='background:#2ecc71'></i>Markets</span>"
    "<span><i style='background:#e056fd'></i>Hotel</span>"
    "<span><i style='background:#f5c869'></i>Event</span>"
    "</div>"
)


def render_plan(
    trip: Trip | None,
    places_by_stop: dict[int, list[Place]] | None = None,
    markers: list[dict] | None = None,
    events: list[dict] | None = None,
    day_events: dict[int, list[dict]] | None = None,
    all_events: list[dict] | None = None,
    hotels_by_stop: dict[int, dict] | None = None,
    budget: dict | None = None,
    flights: list[dict] | None = None,
) -> str:
    if trip is None:
        body = "<h1>No plan yet</h1><p>Run <code>python scripts/seed_plan.py</code> first.</p>"
        return _page("Trip plan", body)

    content = _content_html(
        trip,
        places_by_stop or {},
        day_events or {},
        all_events or [],
        hotels_by_stop or {},
        budget or {},
        flights or [],
    )
    body = (
        '<div class="layout">'
        f'<div class="content">{content}</div>'
        '<div class="mapcol"><div id="map"></div>'
        f"{_LEGEND}"
        '<div id="chat"><div id="chatlog"></div>'
        '<form id="chatform"><input id="chatinput" autocomplete="off" '
        'placeholder="Ask, edit the plan, or manage tasks…"/>'
        "<button>Send</button></form></div></div>"
        f"{_TASKBOARD_HTML}"
        "</div>"
        f"{_map_script(markers or [], events or [])}"
        f"<script>{_TASK_JS}</script>"
        f"<script>{_CHAT_JS}</script>"
        f"<script>{_UI_JS}</script>"
    )
    return _page(trip.name, body)
