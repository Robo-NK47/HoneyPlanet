"""Ingestion pipeline: fetch a URL, extract its main text, and persist a Document row."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from trip_planner.ingest.extract import extract_main_text
from trip_planner.ingest.fetcher import Fetcher
from trip_planner.models import Document, Source


async def ingest_url(
    session: AsyncSession,
    fetcher: Fetcher,
    client: httpx.AsyncClient,
    url: str,
    *,
    source_id: int | None = None,
) -> Document:
    result = await fetcher.fetch(client, url)

    if result.html:
        extracted = extract_main_text(result.html, url)
        content_hash = hashlib.sha256(result.html.encode("utf-8")).hexdigest()
        raw_path: str | None = str(fetcher.cache_path_for(url))
    else:
        extracted = extract_main_text(None)
        content_hash = None
        raw_path = None

    doc = Document(
        source_id=source_id,
        url=url,
        http_status=result.status,
        fetched_at=datetime.now(UTC),
        content_hash=content_hash,
        raw_path=raw_path,
        title=extracted.title,
        extracted_text=extracted.text,
        language=extracted.language,
        word_count=extracted.word_count,
        error=result.error,
    )
    session.add(doc)
    await session.flush()
    return doc


async def ingest_source(
    session: AsyncSession, fetcher: Fetcher, client: httpx.AsyncClient, source: Source
) -> Document:
    return await ingest_url(session, fetcher, client, source.url, source_id=source.id)
