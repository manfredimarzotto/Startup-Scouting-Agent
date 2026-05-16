"""End-to-end orchestration: source -> filter -> enrich -> score -> digest."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from scout.enrichment import (
    enrich_with_claude,
    fetch_careers_signals,
    linkedin_search_urls,
)
from scout.models import FundingEvent, ScoredCompany
from scout.outreach.angle import is_suppressed, load_pipeline_suppression
from scout.scoring import passes_geo_filter, score_company
from scout.sources import LIVE_SOURCES, MockSource
from scout.sources.base import Source
from scout.sources.rss import SourceStats
from scout.storage import ScoutDB

log = logging.getLogger("scout.pipeline")


@dataclass
class PipelineStats:
    """Funnel counts so we can see where companies are being lost.

    Surfaced in the digest header so the operator can diagnose empty runs.
    """

    per_source: dict[str, SourceStats] = field(default_factory=dict)
    already_seen: int = 0
    suppressed: int = 0
    enriched: int = 0
    geo_filter_dropped: int = 0
    geo_filter_passed: int = 0
    scored: int = 0

    @property
    def total_parsed(self) -> int:
        return sum(s.parsed_events for s in self.per_source.values())


@dataclass
class PipelineResult:
    scored: list[ScoredCompany]
    stats: PipelineStats


def load_fit_profile(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def run(
    sources: list[Source],
    fit_profile: dict[str, Any],
    db: ScoutDB,
    suppression: set[str],
    lookback_days: int = 2,
    skip_careers_fetch: bool = False,
) -> PipelineResult:
    """Run the full pipeline. Returns the scored companies + funnel stats.

    Idempotent: events already in the DB are skipped.
    """
    allowed_countries: list[str] = fit_profile["geography"]["allowed_hq_countries"]
    stats = PipelineStats()
    scored: list[ScoredCompany] = []

    for source in sources:
        log.info("fetching from %s", source.name)
        events: list[FundingEvent]
        try:
            events = list(source.fetch(lookback_days=lookback_days))
        except Exception as exc:
            log.warning("source %s failed: %s", source.name, exc)
            stats.per_source[source.name] = SourceStats(error=type(exc).__name__)
            continue

        # Most sources expose a `stats` attribute after fetch (RSS + mock).
        # Synthesize a default for any source that doesn't, so the funnel is
        # still readable.
        source_stats = getattr(source, "stats", None) or SourceStats(
            parsed_events=len(events)
        )
        stats.per_source[source.name] = source_stats

        for event in events:
            if db.has_seen(event.fingerprint()):
                stats.already_seen += 1
                continue
            if is_suppressed(event.company_name, suppression):
                stats.suppressed += 1
                log.info("suppressed %s (in pipeline)", event.company_name)
                continue

            careers = None
            if not skip_careers_fetch:
                careers = fetch_careers_signals(_guess_homepage(event))

            enrichment = enrich_with_claude(event, careers)
            stats.enriched += 1

            if not passes_geo_filter(event, enrichment, allowed_countries):
                stats.geo_filter_dropped += 1
                log.info("geo-filtered %s", event.company_name)
                continue
            stats.geo_filter_passed += 1

            score = score_company(event, enrichment, fit_profile)

            sc = ScoredCompany(
                event=event,
                enrichment=enrichment,
                score=score,
                linkedin_search_urls=linkedin_search_urls(enrichment.company_name),
                has_existing_cfo_flag=enrichment.has_senior_finance_leader is True,
            )
            db.save(sc)
            scored.append(sc)
            stats.scored += 1

    return PipelineResult(scored=scored, stats=stats)


def run_mock(fit_profile: dict[str, Any], db: ScoutDB, suppression: set[str]) -> PipelineResult:
    """End-to-end run on the fixture data. No network, no API calls required."""
    return run(
        sources=[MockSource()],
        fit_profile=fit_profile,
        db=db,
        suppression=suppression,
        skip_careers_fetch=True,
    )


def _guess_homepage(event: FundingEvent) -> str | None:
    """Best-effort: skip for v1. Real implementation needs a search lookup or
    explicit company URL in the source. Returning None means careers enrichment
    is skipped for that event."""
    return None


def default_live_sources() -> list[Source]:
    return [cls() for cls in LIVE_SOURCES]
