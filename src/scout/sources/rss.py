"""Shared RSS scaffolding. Subclasses provide URL + a few hooks."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

import feedparser
import httpx

from scout.models import FundingEvent

log = logging.getLogger("scout.sources.rss")


@dataclass
class SourceStats:
    """Populated by a source after its fetch generator is exhausted."""

    http_status: int | None = None
    raw_entries: int = 0  # entries returned by feedparser before any filter
    in_window: int = 0  # entries within the lookback window
    funding_term_match: int = 0  # entries that mention raise/funding terms
    parsed_events: int = 0  # entries that successfully became FundingEvents
    error: str | None = None  # short error reason if the fetch failed


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
    r"\b(raises?|raised|secures?|closes?|lands?|nets?|bags?|picks up|"
    r"announces|completes?|wraps?|hauls?|grabs?|gets|wins?)\b.*?"
    r"(\$|€|£|usd|eur|gbp|seed|series|funding|round|million|billion)",
    re.IGNORECASE,
)


# Strip leading "London's", "Berlin-based", "<adj> startup" etc. before
# trying to grab the company name.
_NAME_PREFIX_STRIP = re.compile(
    r"^(?:[A-Z][\w']+(?:'s|-based|-headquartered)\s+|"
    r"[A-Z][\w']+\s+(?:startup|scaleup|company|firm)\s+)",
)

# Multi-pattern company name extraction. Tried in order.
_NAME_PATTERNS = [
    # "X raises", "X raised", etc. — strict, name at start of title
    re.compile(
        r"^([A-Z][\w&\.\-]+(?:\s+[A-Z][\w&\.\-]+){0,4})"
        r"\s+(?:raises?|raised|secures?|closes?|lands?|nets?|bags?|"
        r"announces|completes?|wraps?|hauls?|grabs?|gets|wins?)\b"
    ),
    # "Funding for X" / "Investment in X"
    re.compile(
        r"\b(?:funding|investment|capital)\s+(?:for|in)\s+"
        r"([A-Z][\w&\.\-]+(?:\s+[A-Z][\w&\.\-]+){0,3})\b"
    ),
]


# Things that look like capitalized phrases but aren't company names.
# Names matching these (case-insensitive, whole-string) get dropped before
# we waste a Haiku call on them. Learned from real first-run garbage:
# "Marketing", "HTGF Family Day", "Anthropic" (when mentioned, not raising),
# "Sheryl Sandberg-backed", "UK EdTech Multiverse", etc.
_NAME_BLACKLIST = frozenset({
    # Generic English words that match the capitalized-start pattern
    "the", "this", "that", "two", "three", "four", "five",
    "why", "how", "when", "what", "who", "where", "which",
    "marketing", "construction", "fintech", "healthtech", "edtech", "proptech",
    "founder", "founders", "startup", "scaleup", "company", "firm",
    # Geo / sector descriptor prefixes that shouldn't stand alone
    "uk", "us", "eu", "european", "british", "ai", "tech", "deep tech",
    # Investor / VC firms that show up in fundraise headlines
    "anthropic", "openai", "google", "microsoft", "apple", "meta",
    "robinhood", "stripe", "lightrock", "sequoia", "accel", "index", "atomico",
    "htgf family day", "techcrunch", "sifted",
})


# Phrases inside an extracted candidate that mean it's a descriptor, not a
# company name (e.g. "Sheryl Sandberg-backed", "HTGF Family Day"). Checked
# against the candidate AFTER extraction, not the title — real fundraise
# headlines routinely contain "from", "led by", etc.
_PHRASE_DISQUALIFIERS = ("-backed", "backed", "family day", "led by")


class RSSSource:
    """Base class. Sets `name` and `url` on subclasses."""

    name: str = ""
    url: str = ""

    # Override to tighten filtering when the feed is funding-only already.
    require_funding_terms: bool = True

    # HTTP timeout for the RSS fetch itself. Short — failing-fast is better
    # than blocking the daily run on one slow source.
    fetch_timeout: float = 10.0

    def __init__(self) -> None:
        self.stats = SourceStats()

    def fetch(self, lookback_days: int = 2) -> Iterable[FundingEvent]:
        self.stats = SourceStats()  # reset per call
        cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
        try:
            resp = httpx.get(
                self.url,
                headers=_RSS_HEADERS,
                timeout=self.fetch_timeout,
                follow_redirects=True,
            )
        except httpx.HTTPError as exc:
            self.stats.error = type(exc).__name__
            log.warning("rss fetch failed for %s: %s", self.name, exc)
            return

        self.stats.http_status = resp.status_code
        if resp.status_code != 200 or not resp.text:
            self.stats.error = f"HTTP {resp.status_code}"
            log.warning("rss fetch returned HTTP %s for %s", resp.status_code, self.name)
            return

        parsed = feedparser.parse(resp.text)
        self.stats.raw_entries = len(parsed.entries)

        for entry in parsed.entries:
            published = self._entry_datetime(entry)
            if published is None or published < cutoff:
                continue
            self.stats.in_window += 1

            title = (entry.get("title") or "").strip()
            summary = (entry.get("summary") or entry.get("description") or "").strip()
            link = entry.get("link") or ""

            text_blob = f"{title} {summary}"
            if self.require_funding_terms and not _FUNDING_TERMS.search(text_blob):
                continue
            self.stats.funding_term_match += 1

            company = self.extract_company_name(title, summary)
            if not company:
                continue

            self.stats.parsed_events += 1
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
        """Extract company name from a fundraise headline.

        Tries multiple patterns; falls back to the first capitalized phrase
        after stripping common prefixes ("London's ...", "Berlin-based ...",
        "<adj> startup ..."). Names that look like obvious garbage (common
        English words, sector descriptors, well-known VCs/big tech) are
        rejected outright rather than passed to Haiku.
        """
        # Strip leading geo / descriptor prefix so the name patterns see the
        # actual subject of the sentence.
        cleaned = _NAME_PREFIX_STRIP.sub("", title)

        candidate: str | None = None
        for pattern in _NAME_PATTERNS:
            m = pattern.search(cleaned)
            if m:
                candidate = m.group(1).strip()
                break

        if candidate is None:
            # Last-resort fallback: first capitalized phrase in the cleaned title.
            m = re.match(r"([A-Z][\w&\.\-]+(?:\s+[A-Z][\w&\.\-]+){0,2})", cleaned)
            candidate = m.group(1).strip() if m else None

        if candidate is None:
            return None

        # Reject obvious garbage. Saves Haiku tokens and stops the dashboard
        # filling with non-companies.
        lowered_candidate = candidate.lower()
        if lowered_candidate in _NAME_BLACKLIST:
            return None
        # Descriptor phrases that show up captured but aren't company names.
        if any(p in lowered_candidate for p in _PHRASE_DISQUALIFIERS):
            return None
        # All-uppercase short tokens are usually acronyms (UK, EU, AI, HTGF)
        # not company names.
        if len(candidate) <= 4 and candidate.isupper():
            return None

        return candidate

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
