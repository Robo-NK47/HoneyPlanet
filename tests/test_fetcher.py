from __future__ import annotations

import asyncio

import httpx

from trip_planner.ingest.fetcher import Fetcher


def test_fetch_then_serve_from_cache(tmp_path) -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, text="<html><title>Hi</title><body>ok</body></html>")

    transport = httpx.MockTransport(handler)
    fetcher = Fetcher(cache_dir=tmp_path, respect_robots=False, per_host_delay=0)

    async def run() -> tuple:
        async with httpx.AsyncClient(transport=transport) as client:
            first = await fetcher.fetch(client, "https://example.com/a")
            second = await fetcher.fetch(client, "https://example.com/a")
            return first, second

    first, second = asyncio.run(run())

    assert first.status == 200 and first.html and first.from_cache is False
    assert second.from_cache is True
    assert calls["n"] == 1  # the second fetch was served from disk, no new request


def test_robots_block(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /\n")
        return httpx.Response(200, text="<html><body>should not reach</body></html>")

    transport = httpx.MockTransport(handler)
    fetcher = Fetcher(cache_dir=tmp_path, respect_robots=True, per_host_delay=0)

    async def run() -> object:
        async with httpx.AsyncClient(transport=transport) as client:
            return await fetcher.fetch(client, "https://example.com/blocked")

    result = asyncio.run(run())
    assert result.html is None
    assert result.error == "blocked by robots.txt"
