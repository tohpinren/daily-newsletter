"""GitHub repository search fetcher for trending projects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from src.config import SourceDefinition
from src.models import Article

_GITHUB_ACCEPT_HEADER = "application/vnd.github+json"
_GITHUB_API_VERSION = "2022-11-28"


def _build_trending_query(*, lookback_days: int = 7) -> str:
    """Build a GitHub search query for recently active repositories."""
    since_date = (datetime.now(UTC) - timedelta(days=lookback_days)).date().isoformat()
    return f"archived:false pushed:>{since_date}"


def _parse_iso_datetime(*, raw_value: str | None) -> datetime | None:
    """Parse an ISO datetime string from GitHub API."""
    if raw_value is None or raw_value.strip() == "":
        return None
    try:
        return datetime.fromisoformat(raw_value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _repository_to_article(*, repository: dict[str, Any], source: SourceDefinition) -> Article | None:
    """Convert one GitHub repository payload to an Article."""
    full_name = str(repository.get("full_name", "")).strip()
    html_url = str(repository.get("html_url", "")).strip()
    if full_name == "" or html_url == "":
        return None

    description = str(repository.get("description", "")).strip() or None
    stars_value = repository.get("stargazers_count")
    score = int(stars_value) if isinstance(stars_value, int) else None
    updated_at = _parse_iso_datetime(raw_value=str(repository.get("updated_at", "")).strip())

    try:
        return Article(
            title=full_name,
            url=html_url,
            source=source.name,
            section=source.section,
            published_at=updated_at,
            summary=description,
            score=score,
        )
    except Exception:
        return None


async def fetch_github_trending_repositories(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
) -> list[Article]:
    """Fetch trending repositories from GitHub Search API."""
    response = await client.get(
        source.url,
        params={
            "q": _build_trending_query(),
            "sort": "stars",
            "order": "desc",
            "per_page": source.limit,
        },
        headers={
            "Accept": _GITHUB_ACCEPT_HEADER,
            "X-GitHub-Api-Version": _GITHUB_API_VERSION,
        },
        timeout=20.0,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("items")
    if not isinstance(items, list):
        return []

    articles = [
        article
        for article in (
            _repository_to_article(repository=repository, source=source)
            for repository in items
            if isinstance(repository, dict)
        )
        if article is not None
    ]
    return articles[: source.limit]
