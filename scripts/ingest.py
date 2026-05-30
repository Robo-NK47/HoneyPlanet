"""Run ingestion: fetch + extract + persist Documents.

Usage (DB connected):
    python scripts/ingest.py                       # ingest all registered sources
    python scripts/ingest.py https://example.com   # ingest one or more explicit URLs
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import httpx
from sqlalchemy import select

from trip_planner.db import async_session_maker
from trip_planner.ingest.fetcher import Fetcher
from trip_planner.ingest.pipeline import ingest_source, ingest_url
from trip_planner.models import Source


async def run(urls: list[str]) -> None:
    fetcher = Fetcher()
    async with async_session_maker() as session, httpx.AsyncClient() as client:
        if urls:
            for url in urls:
                doc = await ingest_url(session, fetcher, client, url)
                print(f"[{doc.http_status}] {url}  words={doc.word_count}  err={doc.error}")
        else:
            sources = (await session.execute(select(Source))).scalars().all()
            print(f"Ingesting {len(sources)} source(s)…")
            for source in sources:
                doc = await ingest_source(session, fetcher, client, source)
                print(f"[{doc.http_status}] {source.name}  words={doc.word_count}  err={doc.error}")
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch + extract + store web documents.")
    parser.add_argument("urls", nargs="*", help="explicit URLs; if omitted, ingest all sources")
    parser.add_argument("--file", help="path to a newline-separated list of URLs to ingest")
    args = parser.parse_args()
    urls = list(args.urls)
    if args.file:
        lines = Path(args.file).read_text(encoding="utf-8").splitlines()
        urls += [ln.strip() for ln in lines if ln.strip() and not ln.strip().startswith("#")]
    asyncio.run(run(urls))


if __name__ == "__main__":
    main()
