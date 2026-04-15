"""LLM-based article deduplication and summarization."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from datetime import UTC, datetime

import httpx

from src.models import Article, NewsletterSection, SectionName

_MAX_CANDIDATES_FOR_LLM = 100
_MAX_PER_SOURCE_FOR_LLM = 5


def _datetime_for_sort(*, published_at: datetime | None) -> datetime:
    """Normalize timestamps for stable recency ordering (UTC, missing last)."""
    if published_at is None:
        return datetime.min.replace(tzinfo=UTC)
    if published_at.tzinfo is None:
        return published_at.replace(tzinfo=UTC)
    return published_at.astimezone(UTC)


def _llm_candidate_articles(
    *,
    articles: list[Article],
    max_total: int,
    per_source_cap: int,
    rotation_offset: int = 0,
) -> list[Article]:
    """Pick a recency-sorted, source-balanced pool so the model sees varied inputs.

    Raw section lists follow ``build_sources`` order, so the LLM otherwise tends to
    overweight the same early feeds on every run. ``rotation_offset`` changes which
    alphabetical source is visited first so the daily candidate pool shifts.
    """
    if not articles:
        return []
    sorted_by_recency = sorted(
        articles,
        key=lambda a: _datetime_for_sort(published_at=a.published_at),
        reverse=True,
    )
    by_source: dict[str, deque[Article]] = defaultdict(deque)
    for article in sorted_by_recency:
        by_source[article.source].append(article)

    names = sorted(by_source.keys())
    if not names:
        return []
    pivot = rotation_offset % len(names)
    source_names = names[pivot:] + names[:pivot]
    result: list[Article] = []
    counts: dict[str, int] = defaultdict(int)
    seen_urls: set[str] = set()

    while len(result) < max_total:
        progressed = False
        for name in source_names:
            if len(result) >= max_total:
                break
            if counts[name] >= per_source_cap:
                continue
            bucket = by_source[name]
            while bucket:
                item = bucket.popleft()
                url_key = str(item.url)
                if url_key in seen_urls:
                    continue
                seen_urls.add(url_key)
                result.append(item)
                counts[name] += 1
                progressed = True
                break
        if not progressed:
            break

    if len(result) < max_total:
        for article in sorted_by_recency:
            if len(result) >= max_total:
                break
            url_key = str(article.url)
            if url_key in seen_urls:
                continue
            seen_urls.add(url_key)
            result.append(article)

    return result


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
    published: str | None = None
    if article.published_at is not None:
        published = article.published_at.isoformat()
    row: dict[str, object] = {
        "title": article.title,
        "url": str(article.url),
        "source": article.source,
        "summary": article.summary or "",
        "score": article.score,
        "published_at": published,
    }
    if section == "hacker_news":
        row["discussion_url"] = (
            str(article.discussion_url) if article.discussion_url is not None else None
        )
    return row


def _build_llm_prompt(
    *,
    section: SectionName,
    articles: list[Article],
    limit: int,
    edition_date_utc: str,
) -> str:
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
        f"Newsletter edition date (UTC): {edition_date_utc}\n"
        f"Return top {limit} deduplicated items in strict JSON only.\n"
        "Rules:\n"
        "- Deduplicate semantically similar headlines.\n"
        "- Prioritize relevance, significance, and practical interest for software engineers.\n"
        "- Prefer recent items: when published_at is present, favor newer dates; avoid stale picks.\n"
        "- Spread selections across different source names; at most two items from the same "
        "source unless the pool leaves no alternative.\n"
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
    edition_date_utc: str,
) -> list[Article]:
    """Call Gemini model and return curated article list."""
    prompt = _build_llm_prompt(
        section=section,
        articles=articles,
        limit=limit,
        edition_date_utc=edition_date_utc,
    )
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash-lite:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.9,
            "topP": 0.95,
        },
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

    run_time = datetime.now(UTC)
    edition_date_utc = run_time.date().isoformat()
    day_index = run_time.timetuple().tm_yday

    output_sections: list[NewsletterSection] = []
    for section_index, section_name in enumerate(ordered_sections):
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

        candidates = _llm_candidate_articles(
            articles=articles,
            max_total=_MAX_CANDIDATES_FOR_LLM,
            per_source_cap=_MAX_PER_SOURCE_FOR_LLM,
            rotation_offset=day_index + section_index,
        )

        try:
            curated_articles = await _call_gemini_curation(
                api_key=api_key,
                section=section_name,
                articles=candidates,
                limit=limit,
                edition_date_utc=edition_date_utc,
            )
            if not curated_articles:
                curated_articles = _fallback_curate_articles(articles=candidates, limit=limit)
        except Exception:
            curated_articles = _fallback_curate_articles(articles=candidates, limit=limit)

        output_sections.append(
            NewsletterSection(
                name=section_name,
                heading=SECTION_HEADINGS[section_name],
                items=curated_articles,
            )
        )
    return output_sections
