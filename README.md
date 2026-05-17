# Startup Scouting Agent

Daily agent that surfaces UK/EU startups that **just raised** and are at the
"first finance hire" inflection point — ranked as **employers**, not investments,
against a specific candidate profile.

Built for a senior M&A banker transitioning into strategic finance / CFO / founder's
associate roles at AI-native and vertical SaaS startups.

## What it does

1. Pulls funding announcements from 5 RSS sources (TechCrunch, TechFundingNews,
   EU-Startups, Tech.eu, UKTN).
2. Applies a **hard UK/EU geo filter** — US companies are dropped before scoring.
3. For each company, tries to fetch the careers page and detect finance-adjacent
   role openings (CFO, Head of Finance, Strategic Finance, BizOps, Chief of Staff,
   FP&A, etc.).
4. Uses **Claude Haiku 4.5** to enrich each company with stage, investor, founder
   background, finance team state, and a 1–5 finance maturity score.
5. Uses **Claude Haiku 4.5** to score each company on three dimensions:
   finance gap (0–10), personal fit (0–10), reachability (0–5). Composite ranks
   the digest.
6. Renders a markdown digest with rationale, LinkedIn search URLs for manual
   verification, and a suggested outreach angle.
7. Optional: **Claude Sonnet 4.6** weekly synthesis over the last 7 days.

State lives in SQLite — re-runs are idempotent.

## Design decisions baked into v1

- **Sources:** TechCrunch + TechFundingNews + EU-Startups + Tech.eu + UKTN RSS.
  No Crunchbase, no LinkedIn scraping.
- **LinkedIn:** never scraped. The digest embeds search URLs you click through to
  verify finance team composition manually. Avoids ToS issues entirely.
- **Geography:** UK + EU only. US companies are hard-filtered out, even if the
  rest of the signals are strong.
- **CFO already in place:** surfaced with a flag and finance-gap score capped at
  6/10 (rather than filtered out). Keeps Head of Strategic Finance / FP&A Lead
  paths visible.
- **Job boards:** triangulated via the careers-page fetch for funded companies
  only. No independent YC / Wellfound scraping pipeline in v1. The
  `sources/` interface is pluggable for adding one later.
- **Outreach drafting:** the digest includes a one-line suggested angle per
  company; no full draft messages.

## Setup

```bash
# Python 3.11+ required
uv venv && source .venv/bin/activate
uv pip install -e ".[dev]"

cp .env.example .env
# add ANTHROPIC_API_KEY to .env (or export it)
```

## Usage

```bash
# End-to-end run on fixture data — no API key required. Use this first.
scout run-mock

# Daily run against live RSS sources
scout run

# Weekly synthesis over the last 7 days of scored companies
scout synth
```

Digests land in `./digests/YYYY-MM-DD.md`. Weekly synthesis lands in
`./digests/weekly-YYYY-MM-DD.md`. SQLite state lives in `./scout.db`.

## Configuration

- **`config/fit_profile.yaml`** — your candidate profile. Sector depth, target
  roles, allowed countries, warm investor network. Edit freely; scoring prompts
  read this verbatim, so changes here change rationales immediately.
- **`config/companies_in_pipeline.yaml`** — companies already in active
  conversation. Suppressed from the daily digest. Maintain by hand.
- **`prompts/*.md`** — enrichment, scoring, and weekly synthesis prompts, all
  version-controlled. Edit and re-run to A/B prompt changes.

## Adding a source

Each source is ~30 lines. Subclass `RSSSource` for a feed-based one:

```python
# src/scout/sources/my_feed.py
from scout.sources.rss import RSSSource

class MyFeedSource(RSSSource):
    name = "my_feed"
    url = "https://example.com/feed.xml"
    require_funding_terms = True
```

Then add the class to `LIVE_SOURCES` in `src/scout/sources/__init__.py`.

For non-RSS sources, implement the `Source` protocol from `sources/base.py` —
just a `name` attribute and `fetch(lookback_days)` that yields `FundingEvent`.

## Operational notes

- **Cost:** Haiku enrichment + scoring runs at roughly $0.005–$0.01 per company
  with prompt caching on the system prompts. A daily run of ~30 announcements is
  ~$0.30. Weekly Sonnet synthesis is one call, ~$0.05.
- **Rate limits:** RSS feeds use `httpx` with a 6s timeout and a single
  `User-Agent: startup-scouting-agent/0.1 (research)` header. Careers pages get
  the same. No retries — if a fetch fails the company is skipped that day.
- **`robots.txt`:** the RSS-only design respects publisher feed policies by
  construction. Careers-page fetches hit `/careers`, `/jobs`, `/about/careers`
  on the company's own homepage; we don't crawl beyond that.
- **Idempotency:** events are keyed by `source:url` in SQLite. Re-running the
  same day is a no-op. Resetting the DB re-scores everything.

## GitHub Actions

`.github/workflows/daily.yml` runs `scout run` every weekday at 07:00 UTC,
commits the digest, the updated DB, and a regenerated dashboard back to
the repo. Set `ANTHROPIC_API_KEY` as a repo secret.

## Dashboard

Every workflow run regenerates `docs/index.html` from `scout.db` — a single
self-contained dark-mode page with every company ever scored, sortable by
any column, filterable by stage, score, and CFO presence. No build step,
no framework, no external deps.

**To publish it via GitHub Pages:** repo → Settings → Pages → Source: "Deploy
from a branch" → Branch: `main` / `docs` → Save. After the next workflow
run the dashboard lives at `https://<owner>.github.io/<repo>/`.

Regenerate locally any time:
```bash
scout dashboard          # writes docs/index.html from scout.db
open docs/index.html
```

## Roadmap (not in v1)

- Direct YC Work-at-a-Startup / Wellfound scraping for finance roles at
  recently-funded cos (pluggable source adapter).
- Next.js dashboard on Vercel with filters (sector, stage, geography, score).
- Proxycurl or similar for programmatic LinkedIn enrichment.
- Crunchbase News RSS for redundancy and breadth.
- Outreach message drafting for top-3 daily picks.

## Repo layout

```
config/                   # fit_profile + pipeline suppression
prompts/                  # enrichment, scoring, weekly synthesis (all markdown)
src/scout/
    sources/              # RSS + mock + base protocol
    enrichment/           # careers fetch, LinkedIn URL gen, Claude enrichment
    scoring/              # geo filter + scoring rubric
    digest/               # daily digest + weekly synthesis renderers
    storage/              # SQLite idempotency
    outreach/             # pipeline suppression
    pipeline.py           # orchestrator
    cli.py                # entry point
tests/
    fixtures/             # mock funding data
.github/workflows/        # daily CI
digests/                  # output (gitignored except .gitkeep)
```
