"""Web scrapers for non-RSS sources."""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from src.config import SourceDefinition
from src.models import Article


def _extract_links_from_html(
    *,
    html: str,
    base_url: str,
    source: SourceDefinition,
) -> list[Article]:
    """Extract candidate links from page HTML with simple heuristics."""
    soup = BeautifulSoup(markup=html, features="html.parser")
    anchors = soup.select("a[href]")

    articles: list[Article] = []
    seen_urls: set[str] = set()
    for anchor in anchors:
        title = anchor.get_text(strip=True)
        href = str(anchor.get("href", "")).strip()
        if title == "" or href == "":
            continue
        if len(title) < 18:
            continue
        url = urljoin(base_url, href)
        if not url.startswith("http"):
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        try:
            article = Article(
                title=title,
                url=url,
                source=source.name,
                section=source.section,
            )
        except Exception:
            continue

        articles.append(article)
        if len(articles) >= source.limit:
            break
    return articles


async def scrape_articles(
    *,
    source: SourceDefinition,
    client: httpx.AsyncClient,
) -> list[Article]:
    """Scrape articles from generic HTML sources."""
    response = await client.get(source.url, timeout=20.0, follow_redirects=True)
    response.raise_for_status()
    return _extract_links_from_html(
        html=response.text,
        base_url=source.url,
        source=source,
    )
