"""List ingested documents (newest extraction first). Usage: python scripts/show_documents.py"""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from trip_planner.db import async_session_maker
from trip_planner.models import Document


async def main() -> None:
    async with async_session_maker() as session:
        total = await session.scalar(select(func.count(Document.id)))
        result = await session.execute(
            select(
                Document.http_status,
                Document.language,
                Document.word_count,
                Document.title,
                Document.url,
            ).order_by(Document.word_count.desc())
        )
        rows = result.all()

    print(f"documents: {total}")
    for status, lang, wc, title, url in rows:
        title_short = (title or "")[:38]
        print(f"  [{status}] {wc or 0:>4}w  {lang or '-':<3}  {title_short:<40}  {url}")


if __name__ == "__main__":
    asyncio.run(main())
