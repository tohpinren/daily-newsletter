"""Typed models used across the daily newsletter pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


SectionName = Literal[
    "world_news",
    "singapore_asia",
    "tech_swe",
    "fintech_news",
    "ai_ml",
    "hacker_news",
    "engineering_blogs",
]


class Article(BaseModel):
    """Single content item collected from an upstream source."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    title: str = Field(min_length=1)
    url: HttpUrl
    source: str = Field(min_length=1)
    section: SectionName
    published_at: datetime | None = None
    summary: str | None = None
    score: int | None = None
    discussion_url: HttpUrl | None = None


class NewsletterSection(BaseModel):
    """Curated list of articles for one newsletter section."""

    model_config = ConfigDict(extra="forbid")

    name: SectionName
    heading: str = Field(min_length=1)
    items: list[Article] = Field(default_factory=list)


class Newsletter(BaseModel):
    """Top-level newsletter payload ready for email rendering."""

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    sections: list[NewsletterSection] = Field(default_factory=list)
