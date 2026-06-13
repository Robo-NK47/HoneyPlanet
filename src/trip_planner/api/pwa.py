"""PWA endpoints: web app manifest, service worker, and app icon.

Makes /plan installable to a phone home screen and usable offline. The service worker caches
the last-loaded plan page and task board (network-first / stale-while-revalidate) and the
MapLibre library + previously-viewed map tiles (cache-first), so the itinerary is readable on
a subway or in rural Japan with no signal. These three endpoints are intentionally public
(unauthenticated) so the app shell can install and update.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Response

router = APIRouter(tags=["pwa"])

_MANIFEST = {
    "name": "Trip Planner — Japan & Thailand",
    "short_name": "Trip Planner",
    "description": "Offline honeymoon itinerary for Japan & Thailand.",
    "start_url": "/plan",
    "scope": "/",
    "display": "standalone",
    "orientation": "portrait-primary",
    "background_color": "#0f1115",
    "theme_color": "#0f1115",
    "icons": [
        {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any maskable"}
    ],
}

# A torii gate — recognizable at any size; fills the canvas for maskable safe-zone compliance.
_ICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <rect width="512" height="512" fill="#161a20"/>
  <g fill="#e74c3c">
    <rect x="92" y="150" width="328" height="36" rx="8"/>
    <rect x="86" y="138" width="340" height="14" rx="7"/>
    <rect x="122" y="212" width="268" height="26" rx="6"/>
    <rect x="150" y="150" width="36" height="234"/>
    <rect x="326" y="150" width="36" height="234"/>
  </g>
</svg>"""

# Service worker. Kept dependency-free and small. Bump CACHE to invalidate old entries.
_SW_JS = """
const CACHE = 'trip-planner-v1';
const PRECACHE = ['/icon.svg', '/manifest.webmanifest'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(PRECACHE)).then(() => self.skipWaiting()));
});

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

function cachePut(req, res) {
  const copy = res.clone();
  caches.open(CACHE).then((c) => c.put(req, copy));
  return res;
}

function isMapAsset(url) {
  return url.host.indexOf('openfreemap.org') !== -1 ||
         url.host.indexOf('unpkg.com') !== -1;
}

self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;            // never cache writes (/chat, task edits, login)
  const url = new URL(req.url);

  // The plan page (and any navigation): network-first, fall back to the last cached copy.
  if (req.mode === 'navigate') {
    e.respondWith(
      fetch(req).then((res) => cachePut(req, res))
        .catch(() => caches.match(req).then((r) => r || caches.match('/plan')))
    );
    return;
  }

  // Task board JSON: stale-while-revalidate (show instantly, refresh in the background).
  if (url.pathname === '/tasks' && url.origin === self.location.origin) {
    e.respondWith(
      caches.match(req).then((cached) => {
        const net = fetch(req).then((res) => cachePut(req, res)).catch(() => cached);
        return cached || net;
      })
    );
    return;
  }

  // MapLibre library + map tiles/fonts/sprites: cache-first so viewed areas work offline.
  if (isMapAsset(url)) {
    e.respondWith(
      caches.match(req).then((cached) =>
        cached || fetch(req).then((res) => {
          if (res.ok || res.type === 'opaque') cachePut(req, res);
          return res;
        }).catch(() => cached)
      )
    );
  }
});
"""


@router.get("/manifest.webmanifest", include_in_schema=False)
async def manifest() -> Response:
    return Response(json.dumps(_MANIFEST), media_type="application/manifest+json")


@router.get("/icon.svg", include_in_schema=False)
async def icon() -> Response:
    return Response(
        _ICON_SVG, media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"}
    )


@router.get("/sw.js", include_in_schema=False)
async def service_worker() -> Response:
    return Response(
        _SW_JS,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"},
    )
