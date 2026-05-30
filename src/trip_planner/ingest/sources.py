"""Seed source registry + upsert.

Starter seeds are well-known, reliably-available Japan sources. Your trusted Israeli/Hebrew
blogs and Phase-1 discovery results get added on top (this list is a floor, not a ceiling).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from trip_planner.models import Source


@dataclass(frozen=True)
class SeedSource:
    name: str
    url: str
    kind: str
    language: str
    country: str


SEED_SOURCES: list[SeedSource] = [
    SeedSource("Japan-Guide", "https://www.japan-guide.com/", "guide", "en", "jp"),
    SeedSource("Tokyo Cheapo", "https://tokyocheapo.com/", "blog", "en", "jp"),
    SeedSource("JNTO (Japan.travel)", "https://www.japan.travel/en/", "official", "en", "jp"),
    # Israeli / Hebrew sources the user trusts.
    SeedSource("Yapanit (יפנית)", "https://www.yapanit.com/", "blog", "he", "jp"),
    SeedSource(
        "HaConcierge (הקונסיירז')", "https://haconcierge.com/category/יפן/", "blog", "he", "jp"
    ),
    SeedSource("Mr Japan (מר יפן)", "https://www.mrjapan.co.il", "blog", "he", "jp"),
]


async def upsert_sources(session: AsyncSession, seeds: list[SeedSource] = SEED_SOURCES) -> int:
    """Insert any seed whose URL isn't already present. Returns the number added."""
    existing = set((await session.execute(select(Source.url))).scalars().all())
    added = 0
    for seed in seeds:
        if seed.url in existing:
            continue
        session.add(
            Source(
                name=seed.name,
                url=seed.url,
                kind=seed.kind,
                language=seed.language,
                country=seed.country,
                is_seed=True,
            )
        )
        added += 1
    await session.flush()
    return added
