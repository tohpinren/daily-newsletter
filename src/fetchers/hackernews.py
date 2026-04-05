"""Hacker News API fetcher."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import httpx

from src.config import SourceDefinition
from src.models import Article


def _item_to_article(*, item: dict[str, object], source: SourceDefinition) -> Article | None:
    """Convert a Hacker News item payload to an Article.

    When the story has an external URL, ``url`` is that article and ``discussion_url``
    is the Hacker News item page. For text or Ask HN posts with no outbound URL,
    ``url`` is the Hacker News item page and ``discussion_url`` is omitted.
    """
    title = str(item.get("title", "")).strip()
    if title == "":
        return None

    item_id = item.get("id")
    if item_id is None:
        return None

    url_raw = item.get("url")
    url_value = url_raw.strip() if isinstance(url_raw, str) else ""
    hn_url = f"https://news.ycombinator.com/item?id={item_id}"

    timestamp = item.get("time")
    published_at = (
        datetime.fromtimestamp(int(timestamp), tz=UTC)
        if isinstance(timestamp, int)
        else None
    )
    score_value = item.get("score")
    score = int(score_value) if isinstance(score_value, int) else None

    if url_value != "":
        return Article(
            title=title,
            url=url_value,
            source=source.name,
            section=source.section,
            published_at=published_at,
            score=score,
            discussion_url=hn_url,
        )
    return Article(
        title=title,
        url=hn_url,
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
