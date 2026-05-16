"""Shared RSS scaffolding. Subclasses provide URL + a few hooks."""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable

import feedparser
import httpx

from scout.models import FundingEvent

log = logging.getLogger("scout.sources.rss")

# Many publisher feeds 403 the default Python/feedparser User-Agent. Use a
# browser-shaped UA + explicit Accept so we don't get filtered. RSS fetches
# are low-frequency (one call per source per day) so this isn't aggressive.
_BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_RSS_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.8, */*;q=0.5",
    "Accept-Language": "en-US,en;q=0.9",
}

# Match phrases like "raises $5M", "secures €10M", "£12 million", "raised $5.4M Series A"
_FUNDING_TERMS = re.compile(
    r"\b(raises?|raised|secures?|closes?|lands?|nets?|bags?|picks up|announces)\b.*?"
    r"(\$|€|£|usd|eur|gbp|seed|series|funding|round)",
    re.IGNORECASE,
)


class RSSSource:
    """Base class. Sets `name` and `url` on subclasses."""

    name: str = ""
    url: str = ""

    # Override to tighten filtering when the feed is funding-only already.
    require_funding_terms: bool = True

    # HTTP timeout for the RSS fetch itself. Short — failing-fast is better
    # than blocking the daily run on one slow source.
    fetch_timeout: float = 10.0

    def fetch(self, lookback_days: int = 2) -> Iterable[FundingEvent]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        try:
            resp = httpx.get(
                self.url,
                headers=_RSS_HEADERS,
                timeout=self.fetch_timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            log.warning("rss fetch failed for %s: %s", self.name, exc)
            return
        if resp.status_code != 200 or not resp.text:
            log.warning("rss fetch returned HTTP %s for %s", resp.status_code, self.name)
            return

        parsed = feedparser.parse(resp.text)
        for entry in parsed.entries:
            published = self._entry_datetime(entry)
            if published is None or published < cutoff:
                continue

            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            link = entry.get("link") or ""

            text_blob = f"{title} {summary}"
            if self.require_funding_terms and not _FUNDING_TERMS.search(text_blob):
                continue

            company = self.extract_company_name(title, summary)
            if not company:
                continue

            yield FundingEvent(
                source=self.name,
                source_url=link,
                title=title,
                summary=_strip_html(summary)[:2000],
                company_name=company,
                published_at=published,
                raw_hq_hint=self.extract_hq_hint(title, summary),
            )

    @staticmethod
    def _entry_datetime(entry) -> datetime | None:
        for key in ("published_parsed", "updated_parsed"):
            tm = entry.get(key)
            if tm:
                return datetime(*tm[:6], tzinfo=timezone.utc)
        return None

    def extract_company_name(self, title: str, summary: str) -> str | None:
        """Default heuristic: company is the word(s) before 'raises/secures/closes'."""
        m = re.search(
            r"^([A-Z][\w&\.\- ]{1,60}?)\s+(raises?|raised|secures?|closes?|lands?|nets?|bags?)",
            title,
        )
        return m.group(1).strip() if m else None

    def extract_hq_hint(self, title: str, summary: str) -> str | None:
        """Default: look for common European city/country mentions in title+summary."""
        text = f"{title} {summary}"
        cities = (
            "London Paris Berlin Amsterdam Stockholm Dublin Madrid Milan "
            "Rome Munich Helsinki Oslo Copenhagen Zurich Vienna Lisbon "
            "Barcelona Tallinn Vilnius Warsaw Prague Brussels Luxembourg"
        ).split()
        for city in cities:
            if re.search(rf"\b{city}\b", text):
                return city
        return None


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s).strip()
