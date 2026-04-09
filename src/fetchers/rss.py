"""RSS fetcher for generic feed sources."""

from __future__ import annotations

from calendar import timegm
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import feedparser
import httpx

from src.config import SourceDefinition
from src.models import Article


def _parse_published_datetime(*, raw_value: str | None) -> datetime | None:
    """Parse RSS/Atom published timestamp when available."""
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        parsed = parsedate_to_datetime(raw_value.strip())
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
    except (TypeError, ValueError):
        return None


def _struct_time_to_utc(*, value: Any) -> datetime | None:
    """Convert feedparser's published_parsed / updated_parsed tuple to UTC."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(timegm(value), tz=UTC)
    except (OverflowError, OSError, ValueError, TypeError):
        return None


def _entry_best_datetime(*, entry: feedparser.FeedParserDict) -> datetime | None:
    """Resolve best-effort publication time from RSS or Atom fields."""
    for key in ("published_parsed", "updated_parsed"):
        dt = _struct_time_to_utc(value=entry.get(key))
        if dt is not None:
            return dt
    published_raw = str(entry.get("published", "")).strip() or None
    dt = _parse_published_datetime(raw_value=published_raw)
    if dt is not None:
        return dt
    updated_raw = str(entry.get("updated", "")).strip() or None
    return _parse_published_datetime(raw_value=updated_raw)


def _entry_to_article(*, entry: feedparser.FeedParserDict, source: SourceDefinition) -> Article | None:
    """Convert a feedparser entry to an Article object."""
    title = str(entry.get("title", "")).strip()
    link = str(entry.get("link", "")).strip()
    if title == "" or link == "":
        return None

    summary = str(entry.get("summary", "")).strip() or None

    return Article(
        title=title,
        url=link,
        source=source.name,
        section=source.section,
        published_at=_entry_best_datetime(entry=entry),
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
