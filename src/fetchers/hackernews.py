"""Hacker News API fetcher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from src.config import SourceDefinition
from src.models import Article


def _item_to_article(*, item: dict[str, object], source: SourceDefinition) -> Article | None:
    """Convert a Hacker News item payload to an Article."""
    title = str(item.get("title", "")).strip()
    if title == "":
        return None

    item_id = item.get("id")
    url_value = str(item.get("url", "")).strip()
    fallback_url = f"https://news.ycombinator.com/item?id={item_id}"
    url = url_value if url_value != "" else fallback_url

    timestamp = item.get("time")
    published_at = (
        datetime.fromtimestamp(int(timestamp), tz=UTC)
        if isinstance(timestamp, int)
        else None
    )
    score_value = item.get("score")
    score = int(score_value) if isinstance(score_value, int) else None

    return Article(
        title=title,
        url=url,
        source=source.name,
        section=source.section,
        published_at=published_at,
        score=score,
    )


async def fetch_hackernews_articles(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
) -> list[Article]:
    """Fetch HN story IDs and resolve item details."""
    response = await client.get(source.url, timeout=20.0)
    response.raise_for_status()
    story_ids = response.json()
    if not isinstance(story_ids, list):
        return []

    limited_ids = story_ids[: source.limit]
    item_urls = [
        f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json"
        for story_id in limited_ids
    ]
    item_requests = [client.get(item_url, timeout=20.0) for item_url in item_urls]
    item_responses = await asyncio.gather(*item_requests, return_exceptions=True)

    articles: list[Article] = []
    for item_response in item_responses:
        if isinstance(item_response, Exception):
            continue
        if item_response.status_code != 200:
            continue
        payload = item_response.json()
        if not isinstance(payload, dict):
            continue
        article = _item_to_article(item=payload, source=source)
        if article is not None:
            articles.append(article)
    return articles
