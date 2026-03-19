"""LLM-based article deduplication and summarization."""

from __future__ import annotations

import json
from collections import defaultdict

import httpx

from src.models import Article, NewsletterSection, SectionName


SECTION_HEADINGS: dict[SectionName, str] = {
    "world_news": "World/Global Headlines",
    "singapore_asia": "Singapore and Asia",
    "tech_swe": "Tech and Software Engineering",
    "ai_ml": "AI and Machine Learning",
    "hacker_news": "Hacker News Highlights",
    "engineering_blogs": "Engineering Blog Picks",
}


def group_articles_by_section(*, articles: list[Article]) -> dict[SectionName, list[Article]]:
    """Group raw articles by section."""
    grouped: dict[SectionName, list[Article]] = defaultdict(list)
    for article in articles:
        grouped[article.section].append(article)
    return dict(grouped)


def _fallback_curate_articles(*, articles: list[Article], limit: int) -> list[Article]:
    """Deduplicate by title and keep first N entries as fallback."""
    seen_titles: set[str] = set()
    curated: list[Article] = []
    for article in articles:
        key = article.title.strip().lower()
        if key in seen_titles:
            continue
        seen_titles.add(key)
        curated.append(article)
        if len(curated) >= limit:
            break
    return curated


def _build_llm_prompt(*, section: SectionName, articles: list[Article], limit: int) -> str:
    """Build instruction prompt for Gemini output in strict JSON."""
    payload = [
        {
            "title": article.title,
            "url": str(article.url),
            "source": article.source,
            "summary": article.summary or "",
            "score": article.score,
        }
        for article in articles
    ]
    return (
        "You are curating a daily newsletter section.\n"
        f"Section: {section}\n"
        f"Return top {limit} deduplicated items in strict JSON only.\n"
        "Rules:\n"
        "- Deduplicate semantically similar headlines.\n"
        "- Prioritize relevance, significance, and practical interest for software engineers.\n"
        "- Provide concise summaries (1-2 sentences).\n"
        "- Keep title close to source title.\n"
        '- Output format: {"items":[{"title":"...","url":"...","source":"...","summary":"..."}]}\n'
        f"Items:\n{json.dumps(payload, ensure_ascii=True)}"
    )


async def _call_gemini_curation(
    *,
    api_key: str,
    section: SectionName,
    articles: list[Article],
    limit: int,
) -> list[Article]:
    """Call Gemini model and return curated article list."""
    prompt = _build_llm_prompt(section=section, articles=articles, limit=limit)
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-lite:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(
            endpoint,
            params={"key": api_key},
            json=body,
            timeout=60.0,
        )
        response.raise_for_status()
        payload = response.json()

    text = (
        payload.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "{}")
    )
    parsed = json.loads(text)
    items = parsed.get("items", [])

    curated: list[Article] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        url = str(item.get("url", "")).strip()
        source = str(item.get("source", "")).strip() or "Aggregated"
        summary = str(item.get("summary", "")).strip() or None
        if title == "" or url == "":
            continue
        try:
            curated.append(
                Article(
                    title=title,
                    url=url,
                    source=source,
                    section=section,
                    summary=summary,
                )
            )
        except Exception:
            continue
    return curated[:limit]


async def curate_sections_with_llm(
    *,
    api_key: str,
    section_articles: dict[SectionName, list[Article]],
) -> list[NewsletterSection]:
    """Curate all sections with Gemini and fallback logic."""
    section_limits: dict[SectionName, int] = {
        "world_news": 10,
        "singapore_asia": 5,
        "tech_swe": 10,
        "ai_ml": 8,
        "hacker_news": 10,
        "engineering_blogs": 5,
    }
    ordered_sections: list[SectionName] = [
        "world_news",
        "singapore_asia",
        "tech_swe",
        "ai_ml",
        "hacker_news",
        "engineering_blogs",
    ]

    output_sections: list[NewsletterSection] = []
    for section_name in ordered_sections:
        articles = section_articles.get(section_name, [])
        limit = section_limits[section_name]
        if not articles:
            output_sections.append(
                NewsletterSection(
                    name=section_name,
                    heading=SECTION_HEADINGS[section_name],
                    items=[],
                )
            )
            continue

        try:
            curated_articles = await _call_gemini_curation(
                api_key=api_key,
                section=section_name,
                articles=articles,
                limit=limit,
            )
            if not curated_articles:
                curated_articles = _fallback_curate_articles(articles=articles, limit=limit)
        except Exception:
            curated_articles = _fallback_curate_articles(articles=articles, limit=limit)

        output_sections.append(
            NewsletterSection(
                name=section_name,
                heading=SECTION_HEADINGS[section_name],
                items=curated_articles,
            )
        )
    return output_sections
