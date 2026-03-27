"""Main orchestration for daily newsletter generation and delivery."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import httpx

from src.composer import compose_newsletter_html
from src.config import SourceDefinition, build_sources, load_config
from src.fetchers.github import fetch_github_trending_repositories
from src.fetchers.hackernews import fetch_hackernews_articles
from src.fetchers.hashnode import fetch_hashnode_featured_articles
from src.fetchers.rss import fetch_rss_articles
from src.fetchers.scraper import scrape_articles
from src.models import Article, Newsletter
from src.processor import curate_sections_with_llm, group_articles_by_section
from src.sender import send_newsletter_email


async def _fetch_source_with_retry(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
    retries: int = 3,
) -> list[Article]:
    """Fetch a source with retry and exponential backoff."""
    for attempt in range(retries):
        try:
            if source.source_type == "rss":
                return await fetch_rss_articles(source=source, client=client)
            if source.source_type == "api":
                return await fetch_hackernews_articles(source=source, client=client)
            if source.source_type == "scrape":
                return await scrape_articles(source=source, client=client)
            if source.source_type == "hashnode":
                return await fetch_hashnode_featured_articles(source=source, client=client)
            if source.source_type == "github":
                return await fetch_github_trending_repositories(source=source, client=client)
            return []
        except Exception:
            is_last_attempt = attempt == retries - 1
            if is_last_attempt:
                return []
            await asyncio.sleep(2**attempt)
    return []


async def _collect_articles(*, sources: list[SourceDefinition]) -> list[Article]:
    """Collect articles from all configured sources concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [
            _fetch_source_with_retry(source=source, client=client, retries=3) for source in sources
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    articles: list[Article] = []
    for result in results:
        if isinstance(result, Exception):
            continue
        articles.extend(result)
    return articles


async def run_async() -> None:
    """Execute full newsletter pipeline and send output email."""
    config = load_config()
    sources = build_sources(max_articles_per_feed=config.max_articles_per_feed)

    raw_articles = await _collect_articles(sources=sources)
    grouped = group_articles_by_section(articles=raw_articles)
    sections = await curate_sections_with_llm(
        api_key=config.gemini_api_key,
        section_articles=grouped,
    )
    newsletter = Newsletter(generated_at=datetime.now(UTC), sections=sections)
    html_body = compose_newsletter_html(newsletter=newsletter)

    sgt = timezone(offset=timedelta(hours=8))
    today_sgt = datetime.now(sgt).strftime("%Y-%m-%d")
    subject = f"Daily Newsletter - {today_sgt}"
    send_newsletter_email(
        gmail_address=config.gmail_address,
        gmail_app_password=config.gmail_app_password,
        recipient_email=config.recipient_email,
        subject=subject,
        html_body=html_body,
    )


def run() -> None:
    """Synchronous entrypoint for CLI and GitHub Actions."""
    asyncio.run(run_async())


if __name__ == "__main__":
    run()
