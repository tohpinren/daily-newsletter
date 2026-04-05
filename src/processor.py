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
    "fintech_news": "Fintech News",
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


def _article_to_prompt_row(*, article: Article, section: SectionName) -> dict[str, object]:
    """Serialize one article for the curation prompt payload."""
    row: dict[str, object] = {
        "title": article.title,
        "url": str(article.url),
        "source": article.source,
        "summary": article.summary or "",
        "score": article.score,
    }
    if section == "hacker_news":
        row["discussion_url"] = (
            str(article.discussion_url) if article.discussion_url is not None else None
        )
    return row


def _build_llm_prompt(*, section: SectionName, articles: list[Article], limit: int) -> str:
    """Build instruction prompt for Gemini output in strict JSON."""
    payload = [_article_to_prompt_row(article=a, section=section) for a in articles]
    hn_rules = ""
    output_format = '{"items":[{"title":"...","url":"...","source":"...","summary":"..."}]}'
    if section == "hacker_news":
        hn_rules = (
            "- For each item, preserve url (story link) and discussion_url (Hacker News item page) "
            "exactly as given. When discussion_url is null, the story has no external URL and url is "
            "already the HN page.\n"
            "- Do not drop discussion_url when it is non-null.\n"
        )
        output_format = (
            '{"items":[{"title":"...","url":"...","discussion_url":"... or null",'
            '"source":"...","summary":"..."}]}'
        )

    return (
        "You are curating a daily newsletter section.\n"
        f"Section: {section}\n"
        f"Return top {limit} deduplicated items in strict JSON only.\n"
        "Rules:\n"
        "- Deduplicate semantically similar headlines.\n"
        "- Prioritize relevance, significance, and practical interest for software engineers.\n"
        "- Provide concise summaries (1-2 sentences).\n"
        "- Keep title close to source title.\n"
        f"{hn_rules}"
        f"- Output format: {output_format}\n"
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
            discussion_url: str | None = None
            if section == "hacker_news":
                raw_discussion = item.get("discussion_url")
                if raw_discussion is not None:
                    ds = str(raw_discussion).strip()
                    if ds not in ("", "null"):
                        discussion_url = ds
            curated.append(
                Article(
                    title=title,
                    url=url,
                    source=source,
                    section=section,
                    summary=summary,
                    discussion_url=discussion_url,
                )
            )
        except Exception:
            continue
    limited = curated[:limit]
    if section == "hacker_news":
        return _merge_hacker_news_discussion_urls(curated=limited, originals=articles)
    return limited


def _merge_hacker_news_discussion_urls(
    *,
    curated: list[Article],
    originals: list[Article],
) -> list[Article]:
    """Restore discussion_url from source items when the model omits it."""
    by_title: dict[str, Article] = {
        a.title.strip().lower(): a for a in originals if a.section == "hacker_news"
    }
    merged: list[Article] = []
    for item in curated:
        if item.discussion_url is not None:
            merged.append(item)
            continue
        match = by_title.get(item.title.strip().lower())
        if match is not None and match.discussion_url is not None:
            merged.append(
                item.model_copy(update={"discussion_url": match.discussion_url}, deep=False)
            )
        else:
            merged.append(item)
    return merged


async def curate_sections_with_llm(
    *,
    api_key: str,
    section_articles: dict[SectionName, list[Article]],
) -> list[NewsletterSection]:
    """Curate all sections with Gemini and fallback logic.

    Most sections return at most ten deduplicated items; fintech and engineering
    blog picks are capped at five after curation.
    """
    default_items_per_section = 10
    ordered_sections: list[SectionName] = [
        "world_news",
        "singapore_asia",
        "tech_swe",
        "fintech_news",
        "ai_ml",
        "hacker_news",
        "engineering_blogs",
    ]
    section_limits: dict[SectionName, int] = {
        name: default_items_per_section for name in ordered_sections
    }
    section_limits["fintech_news"] = 5
    section_limits["engineering_blogs"] = 5

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
