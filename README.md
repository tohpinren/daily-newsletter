# daily-newsletter

Python pipeline that pulls headlines and engineering posts from RSS feeds, Hacker News, light scrapers, Hashnode’s public GraphQL API, and GitHub repository search, curates each section with **Google Gemini**, renders HTML, and sends email via **Gmail SMTP**. A **GitHub Actions** workflow runs it on a schedule (Singapore morning, via UTC cron).

## Sections

Each section is capped at **10** items after LLM curation, except **Fintech News**, which is capped at **5**.

| Section | Role |
|--------|------|
| World / Global | Major wire and newspaper world feeds |
| Singapore and Asia | CNA, ST, BT, SCMP Asia |
| Tech and Software Engineering | Tech media, dev communities, launch sites, Hashnode featured, and trending GitHub repositories |
| Fintech News | Payments, digital banking, and fintech trade RSS (five items after curation) |
| AI and Machine Learning | Labs, research outlets, and AI news sites |
| Hacker News | Top and best story IDs from the Firebase API |
| Engineering Blog Picks | Company and infrastructure engineering blogs |

Source list lives in `src/config.py` (`build_sources`).

## Configuration

Set environment variables (see `.env.example`):

- `GEMINI_API_KEY` – Google AI Studio / Gemini API key
- `GMAIL_ADDRESS` – Gmail account used to send
- `GMAIL_APP_PASSWORD` – Gmail app password (16 characters, **no spaces**)
- `RECIPIENT_EMAIL` – Inbox that receives the digest
- `MAX_ARTICLES_PER_FEED` – Optional; default `10` (per upstream source before curation)

For GitHub Actions, add the same values as **repository secrets** (`Settings` → `Secrets and variables` → `Actions`).

## Local run

```bash
uv sync
export GEMINI_API_KEY=...
export GMAIL_ADDRESS=...
export GMAIL_APP_PASSWORD=...
export RECIPIENT_EMAIL=...
uv run daily-newsletter
```

## Notes

- **GitHub `schedule` is best-effort**; runs can be delayed when load is high.
- **Hashnode** has no stable global HTML RSS for the main feed; this project uses the public **`FEATURED`** GraphQL feed at `https://gql.hashnode.com/`.
- **Artificial Intelligence News** uses the RSS at `https://artificialintelligence-news.com/feed/` (the “AI-News.com” product; other domains did not expose a reliable public RSS in testing).
- **Scrapers** (e.g. TLDR, DevHunt) can break if site HTML changes; RSS sources are more stable.
