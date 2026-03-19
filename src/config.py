"""Configuration helpers and source definitions."""

from __future__ import annotations

from dataclasses import dataclass
from os import getenv
from typing import Literal

from src.models import SectionName


SourceType = Literal["rss", "api", "scrape"]


@dataclass(frozen=True, slots=True)
class SourceDefinition:
    """Single source definition consumed by the pipeline."""

    name: str
    url: str
    source_type: SourceType
    section: SectionName
    limit: int = 10


@dataclass(frozen=True, slots=True)
class AppConfig:
    """Validated runtime configuration for newsletter execution."""

    gemini_api_key: str
    gmail_address: str
    gmail_app_password: str
    recipient_email: str
    max_articles_per_feed: int


def _required_env(*, name: str) -> str:
    """Return required env var value or raise a descriptive error."""
    value = getenv(name)
    if value is None or value.strip() == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value.strip()


def load_config() -> AppConfig:
    """Load and validate runtime config from environment variables."""
    raw_limit = getenv("MAX_ARTICLES_PER_FEED", "10").strip()
    max_articles = int(raw_limit)
    if max_articles < 1:
        raise ValueError("MAX_ARTICLES_PER_FEED must be greater than zero.")

    return AppConfig(
        gemini_api_key=_required_env(name="GEMINI_API_KEY"),
        gmail_address=_required_env(name="GMAIL_ADDRESS"),
        gmail_app_password=_required_env(name="GMAIL_APP_PASSWORD"),
        recipient_email=_required_env(name="RECIPIENT_EMAIL"),
        max_articles_per_feed=max_articles,
    )


def build_sources(*, max_articles_per_feed: int) -> list[SourceDefinition]:
    """Build all source definitions used by fetchers."""
    return [
        SourceDefinition(
            name="Reuters World",
            url="https://www.reuters.com/arc/outboundfeeds/newsroom/all/?outputType=xml",
            source_type="rss",
            section="world_news",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="BBC World",
            url="https://feeds.bbci.co.uk/news/world/rss.xml",
            source_type="rss",
            section="world_news",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="CNN Top Stories",
            url="http://rss.cnn.com/rss/edition.rss",
            source_type="rss",
            section="world_news",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="NYT World",
            url="https://rss.nytimes.com/services/xml/rss/nyt/World.xml",
            source_type="rss",
            section="world_news",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="CNA Latest",
            url="https://www.channelnewsasia.com/rss/latest",
            source_type="rss",
            section="singapore_asia",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="MIT Technology Review",
            url="https://www.technologyreview.com/feed/",
            source_type="rss",
            section="ai_ml",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Changelog",
            url="https://changelog.com/feed",
            source_type="rss",
            section="tech_swe",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Cloudflare Blog",
            url="https://blog.cloudflare.com/rss/",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Netflix Tech Blog",
            url="https://netflixtechblog.com/feed",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Uber Engineering",
            url="https://www.uber.com/blog/engineering/rss/",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Meta Engineering",
            url="https://engineering.fb.com/feed/",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="OpenAI Blog",
            url="https://openai.com/news/rss.xml",
            source_type="rss",
            section="ai_ml",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Anthropic News",
            url="https://www.anthropic.com/news/rss.xml",
            source_type="rss",
            section="ai_ml",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Google DeepMind Blog",
            url="https://deepmind.google/blog/rss.xml",
            source_type="rss",
            section="ai_ml",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="CockroachDB Blog",
            url="https://www.cockroachlabs.com/blog/rss/",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="Yugabyte Blog",
            url="https://www.yugabyte.com/blog/feed/",
            source_type="rss",
            section="engineering_blogs",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="HN Top Stories",
            url="https://hacker-news.firebaseio.com/v0/topstories.json",
            source_type="api",
            section="hacker_news",
            limit=15,
        ),
        SourceDefinition(
            name="HN Best Stories",
            url="https://hacker-news.firebaseio.com/v0/beststories.json",
            source_type="api",
            section="hacker_news",
            limit=10,
        ),
        SourceDefinition(
            name="TLDR Tech",
            url="https://tldr.tech/",
            source_type="scrape",
            section="tech_swe",
            limit=max_articles_per_feed,
        ),
        SourceDefinition(
            name="DevHunt",
            url="https://devhunt.org/",
            source_type="scrape",
            section="tech_swe",
            limit=max_articles_per_feed,
        ),
    ]
