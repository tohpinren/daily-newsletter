"""Email body composition for newsletter output."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models import Newsletter


def compose_newsletter_html(*, newsletter: Newsletter) -> str:
    """Render newsletter HTML from a Jinja template."""
    template_dir = Path(__file__).parent / "templates"
    env = Environment(
        loader=FileSystemLoader(searchpath=str(template_dir)),
        autoescape=select_autoescape(enabled_extensions=("html",)),
    )
    template = env.get_template("newsletter.html")
    return template.render(
        generated_at=newsletter.generated_at.astimezone(UTC).isoformat(),
        sections=newsletter.sections,
    )
