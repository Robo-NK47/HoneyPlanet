"""Build the graphify knowledge graph over the scraped document corpus.

Exports each scraped document's main text to data/corpus/, then runs the real `graphify`
(Claude backend) to produce data/graphify-out/graph.json — which the chat agent can query.

Usage (DB + ANTHROPIC_API_KEY configured):  python scripts/build_graph.py
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy import select

from trip_planner.config import settings
from trip_planner.db import async_session_maker
from trip_planner.models import Document

# Corpus lives OUTSIDE the repo: graphify respects .gitignore, and data/ is ignored.
CORPUS = Path(tempfile.gettempdir()) / "honeyplanet-corpus"
MIN_WORDS = 30


async def export_corpus() -> int:
    CORPUS.mkdir(parents=True, exist_ok=True)
    for old in CORPUS.glob("*.md"):
        old.unlink()
    written = 0
    async with async_session_maker() as session:
        docs = (
            await session.execute(select(Document).where(Document.extracted_text.isnot(None)))
        ).scalars().all()
        for d in docs:
            text = (d.extracted_text or "").strip()
            if len(text.split()) < MIN_WORDS:
                continue
            title = d.title or d.url or f"document {d.id}"
            (CORPUS / f"{d.id:03d}.md").write_text(
                f"# {title}\nSource: {d.url}\n\n{text}\n", encoding="utf-8"
            )
            written += 1
    return written


async def main() -> None:
    count = await export_corpus()
    print(f"Exported {count} documents to {CORPUS}/")
    if count == 0:
        raise SystemExit("No documents to graph; run scripts/ingest.py first.")
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set in .env")

    env = {**os.environ, "ANTHROPIC_API_KEY": settings.anthropic_api_key}
    cmd = [
        sys.executable, "-m", "graphify", "extract", str(CORPUS),
        "--backend", "claude", "--out", "data", "--token-budget", "40000",
    ]
    print("Running: graphify " + " ".join(cmd[3:]))
    proc = subprocess.run(cmd, env=env)
    if proc.returncode == 0:
        print("Graph built: data/graphify-out/graph.json")
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    asyncio.run(main())
