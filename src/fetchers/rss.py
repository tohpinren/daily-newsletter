"""RSS fetcher for generic feed sources."""

from __future__ import annotations

from datetime import datetime
from email.utils import parsedate_to_datetime

import feedparser
import httpx

from src.config import SourceDefinition
from src.models import Article


def _parse_published_datetime(*, raw_value: str | None) -> datetime | None:
    """Parse RSS/Atom published timestamp when available."""
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        return parsedate_to_datetime(raw_value.strip())
    except (TypeError, ValueError):
        return None


def _entry_to_article(*, entry: feedparser.FeedParserDict, source: SourceDefinition) -> Article | None:
    """Convert a feedparser entry to an Article object."""
    title = str(entry.get("title", "")).strip()
    link = str(entry.get("link", "")).strip()
    if title == "" or link == "":
        return None

    published_raw = str(entry.get("published", "")).strip() or None
    summary = str(entry.get("summary", "")).strip() or None

    return Article(
        title=title,
        url=link,
        source=source.name,
        section=source.section,
        published_at=_parse_published_datetime(raw_value=published_raw),
        summary=summary,
    )


async def fetch_rss_articles(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
) -> list[Article]:
    """Fetch and parse one RSS feed into typed articles."""
    response = await client.get(source.url, timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    parsed = feedparser.parse(response.text)

    entries = parsed.entries[: source.limit]
    articles = [
        article
        for article in (
            _entry_to_article(entry=entry, source=source) for entry in entries
        )
        if article is not None
    ]
    return articles
