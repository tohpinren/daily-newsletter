"""Hashnode public GraphQL feed fetcher."""

from __future__ import annotations

from typing import Any

import httpx

from src.config import SourceDefinition
from src.models import Article

_HASHNODE_GQL_URL = "https://gql.hashnode.com/"
_FEATURED_FEED_QUERY = """
query FeaturedFeed($first: Int!) {
  feed(first: $first, filter: { type: FEATURED }) {
    edges {
      node {
        title
        url
      }
    }
  }
}
"""


def _extract_feed_edges(*, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Return feed edge nodes from a Hashnode GraphQL response body."""
    errors = payload.get("errors")
    if isinstance(errors, list) and len(errors) > 0:
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    feed = data.get("feed")
    if not isinstance(feed, dict):
        return []
    edges = feed.get("edges")
    if not isinstance(edges, list):
        return []
    return [edge for edge in edges if isinstance(edge, dict)]


async def fetch_hashnode_featured_articles(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
) -> list[Article]:
    """Fetch featured developer stories from Hashnode via the public GraphQL API.

    Hashnode does not expose a stable global RSS endpoint for the main site feed.
    The FEATURED feed returns curated technical posts suitable for aggregation.
    """
    body = {
        "query": _FEATURED_FEED_QUERY,
        "variables": {"first": source.limit},
    }
    response = await client.post(
        _HASHNODE_GQL_URL,
        json=body,
        headers={"Content-Type": "application/json"},
        timeout=25.0,
    )
    response.raise_for_status()
    payload = response.json()

    articles: list[Article] = []
    for edge in _extract_feed_edges(payload=payload):
        node = edge.get("node")
        if not isinstance(node, dict):
            continue
        title = str(node.get("title", "")).strip()
        url = str(node.get("url", "")).strip()
        if title == "" or url == "":
            continue
        try:
            articles.append(
                Article(
                    title=title,
                    url=url,
                    source=source.name,
                    section=source.section,
                )
            )
        except Exception:
            continue
    return articles[: source.limit]
