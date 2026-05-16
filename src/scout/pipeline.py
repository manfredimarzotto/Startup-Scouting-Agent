"""End-to-end orchestration: source -> filter -> enrich -> score -> digest."""

from __future__ import annotations

import logging
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
from scout.storage import ScoutDB

log = logging.getLogger("scout.pipeline")


def load_fit_profile(path: str | Path) -> dict[str, Any]:
    return yaml.safe_load(Path(path).read_text())


def run(
    sources: list[Source],
    fit_profile: dict[str, Any],
    db: ScoutDB,
    suppression: set[str],
    lookback_days: int = 2,
    skip_careers_fetch: bool = False,
) -> list[ScoredCompany]:
    """Run the full pipeline. Returns the list of newly-scored companies this run.

    Idempotent: events already in the DB are skipped.
    """
    allowed_countries: list[str] = fit_profile["geography"]["allowed_hq_countries"]
    scored: list[ScoredCompany] = []

    for source in sources:
        log.info("fetching from %s", source.name)
        events: Iterable[FundingEvent]
        try:
            events = list(source.fetch(lookback_days=lookback_days))
        except Exception as exc:
            log.warning("source %s failed: %s", source.name, exc)
            continue

        for event in events:
            if db.has_seen(event.fingerprint()):
                continue
            if is_suppressed(event.company_name, suppression):
                log.info("suppressed %s (in pipeline)", event.company_name)
                continue

            careers = None
            if not skip_careers_fetch:
                careers = fetch_careers_signals(_guess_homepage(event))

            enrichment = enrich_with_claude(event, careers)

            if not passes_geo_filter(event, enrichment, allowed_countries):
                log.info("geo-filtered %s", event.company_name)
                continue

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

    return scored


def run_mock(fit_profile: dict[str, Any], db: ScoutDB, suppression: set[str]) -> list[ScoredCompany]:
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
