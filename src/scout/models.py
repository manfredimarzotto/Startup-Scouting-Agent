"""Core data models. Pydantic so the Claude API can parse directly into them."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Stage = Literal["pre-seed", "seed", "series_a", "series_b", "series_c+", "unknown"]
FounderBackground = Literal["technical", "commercial", "mixed", "unknown"]


class FundingEvent(BaseModel):
    """Raw funding announcement as pulled from a source."""

    source: str
    source_url: str
    title: str
    summary: str
    company_name: str
    published_at: datetime
    raw_hq_hint: str | None = None  # whatever the source said about location

    def fingerprint(self) -> str:
        """Stable ID for dedup. Source + URL is enough; companies are sometimes
        announced across multiple outlets and we'll surface the highest-quality one."""
        return f"{self.source}:{self.source_url}"


class CompanyEnrichment(BaseModel):
    """Output of the enrichment step. Either Claude-derived or heuristic."""

    company_name: str
    hq_city: str | None = None
    hq_country: str | None = None
    stage: Stage = "unknown"
    round_amount_usd: int | None = None
    total_raised_usd: int | None = None
    lead_investor: str | None = None
    other_investors: list[str] = Field(default_factory=list)
    sector: str | None = None
    founder_background: FounderBackground = "unknown"
    has_senior_finance_leader: bool | None = None
    senior_finance_leader_name: str | None = None
    open_finance_roles: list[str] = Field(default_factory=list)
    finance_maturity_score: int = Field(default=3, ge=1, le=5)
    notes: str | None = None


class CompanyScore(BaseModel):
    """Output of the scoring step."""

    finance_gap_score: int = Field(ge=0, le=10)
    personal_fit_score: int = Field(ge=0, le=10)
    reachability_score: int = Field(ge=0, le=5)
    rationale: str
    suggested_outreach_angle: str

    @property
    def composite(self) -> float:
        # Weighted: finance gap is the primary signal, fit is secondary,
        # reachability breaks ties. 60 / 30 / 10.
        return (
            self.finance_gap_score * 0.6
            + self.personal_fit_score * 0.3
            + self.reachability_score * 2 * 0.1
        )


class ScoredCompany(BaseModel):
    """A funding event plus enrichment plus score, ready to render."""

    event: FundingEvent
    enrichment: CompanyEnrichment
    score: CompanyScore
    linkedin_search_urls: dict[str, str] = Field(default_factory=dict)
    has_existing_cfo_flag: bool = False
