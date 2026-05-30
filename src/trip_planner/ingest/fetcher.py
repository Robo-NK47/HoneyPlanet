"""Polite async HTTP fetcher: respects robots.txt, rate-limits per host, caches HTML on disk."""

from __future__ import annotations

import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

from trip_planner.ingest.robots import DEFAULT_UA, can_fetch, robots_url_for

DEFAULT_CACHE_DIR = Path("data/cache")


@dataclass
class FetchResult:
    url: str
    status: int | None
    html: str | None
    from_cache: bool
    error: str | None = None


class Fetcher:
    """Reusable fetcher. Inject an httpx.AsyncClient per call so it's easy to test/mocked."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_UA,
        per_host_delay: float = 1.0,
        timeout: float = 20.0,
        cache_dir: Path | str = DEFAULT_CACHE_DIR,
        respect_robots: bool = True,
    ) -> None:
        self.user_agent = user_agent
        self.per_host_delay = per_host_delay
        self.timeout = timeout
        self.cache_dir = Path(cache_dir)
        self.respect_robots = respect_robots
        self._robots: dict[str, str | None] = {}
        self._last_fetch: dict[str, float] = {}
        self._host_locks: dict[str, asyncio.Lock] = {}

    def cache_path_for(self, url: str) -> Path:
        digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]
        host = urlparse(url).netloc or "unknown"
        return self.cache_dir / host / f"{digest}.html"

    def _lock_for(self, host: str) -> asyncio.Lock:
        return self._host_locks.setdefault(host, asyncio.Lock())

    async def _throttle(self, host: str) -> None:
        if self.per_host_delay <= 0:
            return
        last = self._last_fetch.get(host)
        if last is not None:
            wait = self.per_host_delay - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_fetch[host] = time.monotonic()

    async def _get_robots(self, client: httpx.AsyncClient, url: str) -> str | None:
        host = urlparse(url).netloc
        if host not in self._robots:
            try:
                resp = await client.get(
                    robots_url_for(url),
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                )
                self._robots[host] = resp.text if resp.status_code == 200 else None
            except httpx.HTTPError:
                self._robots[host] = None
        return self._robots[host]

    async def fetch(
        self, client: httpx.AsyncClient, url: str, *, use_cache: bool = True
    ) -> FetchResult:
        path = self.cache_path_for(url)
        if use_cache and path.exists():
            return FetchResult(
                url=url, status=200, html=path.read_text(encoding="utf-8"), from_cache=True
            )

        if self.respect_robots:
            robots_txt = await self._get_robots(client, url)
            if not can_fetch(robots_txt, url, self.user_agent):
                return FetchResult(
                    url=url, status=None, html=None, from_cache=False,
                    error="blocked by robots.txt",
                )

        host = urlparse(url).netloc
        async with self._lock_for(host):
            await self._throttle(host)
            try:
                resp = await client.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout,
                    follow_redirects=True,
                )
            except httpx.HTTPError as exc:
                return FetchResult(
                    url=url, status=None, html=None, from_cache=False, error=str(exc)
                )

        html = resp.text
        if resp.status_code == 200 and html:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html, encoding="utf-8")
            return FetchResult(url=url, status=200, html=html, from_cache=False)
        return FetchResult(url=url, status=resp.status_code, html=None, from_cache=False)
