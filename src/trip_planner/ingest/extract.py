"""Main-text extraction from raw HTML. Pure functions — no network, easy to test."""

from __future__ import annotations

from dataclasses import dataclass

import trafilatura
from selectolax.parser import HTMLParser


@dataclass
class Extracted:
    title: str | None
    text: str | None
    language: str | None
    word_count: int


def _title(html: str) -> str | None:
    try:
        node = HTMLParser(html).css_first("title")
        return node.text(strip=True) if node else None
    except Exception:  # noqa: BLE001 — never let title parsing break ingestion
        return None


def _language(html: str) -> str | None:
    """Best-effort language from the <html lang="…"> attribute (e.g. 'he', 'en', 'ja')."""
    try:
        node = HTMLParser(html).css_first("html")
        lang = node.attributes.get("lang") if node else None
        return lang.split("-")[0] if lang else None
    except Exception:  # noqa: BLE001
        return None


def extract_main_text(html: str | None, url: str | None = None) -> Extracted:
    if not html:
        return Extracted(title=None, text=None, language=None, word_count=0)
    text = trafilatura.extract(html, url=url, include_comments=False, include_tables=False)
    return Extracted(
        title=_title(html),
        text=text or None,
        language=_language(html),
        word_count=len(text.split()) if text else 0,
    )
