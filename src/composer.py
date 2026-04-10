"""Email body composition for newsletter output."""

from __future__ import annotations

import re
from pathlib import Path
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import Newsletter

SGT = ZoneInfo("Asia/Singapore")

_MAX_SUMMARY_CHARS = 600
_PLACEHOLDER_SUMMARIES = frozenset(
    {
        "none",
        "null",
        "n/a",
        "none selected",
    }
)


def plain_text_summary_from_html(*, raw: str | None, max_chars: int = _MAX_SUMMARY_CHARS) -> str | None:
    """Strip HTML and whitespace from a summary so email bodies stay readable.

    RSS feeds often put full article HTML in ``summary``; the LLM may also echo
    markup. Returns ``None`` when there is nothing meaningful to show.
    """
    if raw is None:
        return None
    text = raw.strip()
    if text == "":
        return None
    if text.lower() in _PLACEHOLDER_SUMMARIES:
        return None
    if "<" in text and ">" in text:
        soup = BeautifulSoup(markup=text, features="html.parser")
        text = soup.get_text(separator=" ", strip=True)
    text = re.sub(pattern=r"\s+", repl=" ", string=text).strip()
    if text == "":
        return None
    if text.lower() in _PLACEHOLDER_SUMMARIES:
        return None
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "\u2026"
    return text


def _plain_summary_filter(raw: object) -> str:
    """Jinja filter: plain-text summary for HTML email, or empty string."""
    if not isinstance(raw, str):
        return ""
    result = plain_text_summary_from_html(raw=raw, max_chars=_MAX_SUMMARY_CHARS)
    return result if result is not None else ""


def compose_newsletter_html(*, newsletter: Newsletter) -> str:
    """Render newsletter HTML from a Jinja template."""
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(searchpath=str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=("html",)),
    )
    env.filters["plain_summary"] = _plain_summary_filter
    template = env.get_template("newsletter.html")
    return template.render(
        generated_at=newsletter.generated_at.astimezone(SGT).strftime("%Y-%m-%d %H:%M:%S SGT"),
        sections=newsletter.sections,
    )
