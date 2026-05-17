"""Core data models. Pydantic so the Claude API can parse directly into them."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Stage = Literal["pre-seed", "seed", "series_a", "series_b", "series_c+", "unknown"]
FounderBackground = Literal["technical", "commercial", "mixed", "unknown"]


# Pydantic's ge/le constraints translate to JSON Schema minimum/maximum,
# which the Anthropic structured-outputs API rejects with a 400. We strip
# constraints from the schema and clamp the values client-side via
# field_validators below.


def _clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, v))


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
    finance_maturity_score: int = 3
    notes: str | None = None

    @field_validator("finance_maturity_score")
    @classmethod
    def _clamp_maturity(cls, v: int) -> int:
        return _clamp(v, 1, 5)


class CompanyScore(BaseModel):
    """Output of the scoring step."""

    finance_gap_score: int = 0
    personal_fit_score: int = 0
    reachability_score: int = 0
    rationale: str
    suggested_outreach_angle: str

    @field_validator("finance_gap_score", "personal_fit_score")
    @classmethod
    def _clamp_0_10(cls, v: int) -> int:
        return _clamp(v, 0, 10)

    @field_validator("reachability_score")
    @classmethod
    def _clamp_0_5(cls, v: int) -> int:
        return _clamp(v, 0, 5)

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
