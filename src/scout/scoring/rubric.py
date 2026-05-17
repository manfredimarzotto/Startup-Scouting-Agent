"""Scoring orchestrator.

Calls Haiku with the fit profile + enrichment to produce three scores and a
rationale. Falls back to a deterministic heuristic when there's no API key
so the mock end-to-end run still works.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import anthropic
import yaml
from pydantic import ValidationError

from scout.enrichment.claude import _extract_json  # reuse the JSON extractor
from scout.models import CompanyEnrichment, CompanyScore, FundingEvent

log = logging.getLogger("scout.scoring.rubric")

_HAIKU = "claude-haiku-4-5"
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


_JSON_OUTPUT_INSTRUCTION = """
Return ONLY a JSON object (no prose, no markdown fence) with these fields:
  finance_gap_score (integer 0-10)
  personal_fit_score (integer 0-10)
  reachability_score (integer 0-5)
  rationale (string)
  suggested_outreach_angle (string)
"""


def score_company(
    event: FundingEvent,
    enrichment: CompanyEnrichment,
    fit_profile: dict[str, Any],
    client: anthropic.Anthropic | None = None,
) -> CompanyScore:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _heuristic_score(enrichment, fit_profile)

    client = client or anthropic.Anthropic(timeout=30.0)
    system_prompt = (_PROMPTS_DIR / "scoring.md").read_text() + _JSON_OUTPUT_INSTRUCTION

    user_blob = _format_inputs(event, enrichment, fit_profile)

    try:
        response = client.messages.create(
            model=_HAIKU,
            max_tokens=800,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                },
                {
                    "type": "text",
                    "text": "Candidate fit profile:\n" + yaml.safe_dump(fit_profile),
                    "cache_control": {"type": "ephemeral"},
                },
            ],
            messages=[{"role": "user", "content": user_blob}],
        )
    except anthropic.BadRequestError as exc:
        log.warning(
            "scoring 400 for %s: %s",
            enrichment.company_name,
            str(exc).splitlines()[0][:300] if str(exc).strip() else "BadRequestError",
        )
        return _heuristic_score(enrichment, fit_profile)
    except Exception as exc:
        log.warning(
            "scoring failed for %s: %s",
            enrichment.company_name,
            type(exc).__name__,
        )
        return _heuristic_score(enrichment, fit_profile)

    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        json_text = _extract_json(text)
        score = CompanyScore.model_validate_json(json_text)
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning(
            "scoring JSON parse failed for %s: %s. Raw text: %s",
            enrichment.company_name,
            type(exc).__name__,
            text[:200],
        )
        return _heuristic_score(enrichment, fit_profile)

    # Enforce the "CFO present -> cap finance gap at 6" rule even if the LLM ignored it.
    if enrichment.has_senior_finance_leader is True and score.finance_gap_score > 6:
        score = score.model_copy(update={"finance_gap_score": 6})

    return score


def _format_inputs(
    event: FundingEvent, enrichment: CompanyEnrichment, fit_profile: dict[str, Any]
) -> str:
    return (
        f"# Funding event\n{event.model_dump_json(indent=2)}\n\n"
        f"# Enrichment\n{enrichment.model_dump_json(indent=2)}\n"
    )


# ---------------------------------------------------------------------------
# Heuristic fallback
# ---------------------------------------------------------------------------

def _heuristic_score(
    enrichment: CompanyEnrichment, fit_profile: dict[str, Any]
) -> CompanyScore:
    finance_gap = {1: 9, 2: 7, 3: 5, 4: 4, 5: 1}[enrichment.finance_maturity_score]

    if enrichment.has_senior_finance_leader is True:
        finance_gap = min(finance_gap, 6)

    if enrichment.stage in ("series_a", "series_b"):
        finance_gap = min(10, finance_gap + 1)

    sector_high = [s.lower() for s in fit_profile.get("sector_depth", {}).get("high", [])]
    sector_low = [s.lower() for s in fit_profile.get("sector_depth", {}).get("low_or_avoid", [])]
    sector = (enrichment.sector or "").lower()

    personal_fit = 5
    if any(s in sector for s in sector_high):
        personal_fit = 8
    if any(s in sector for s in sector_low):
        personal_fit = min(personal_fit, 4)
    if "ai" in sector:
        personal_fit = min(10, personal_fit + 1)

    warm = [i.lower() for i in fit_profile.get("reachability_signals", {}).get(
        "warm_investor_network", []
    )]
    lead = (enrichment.lead_investor or "").lower()
    reachability = 3 if any(w in lead for w in warm) else 1

    cfo_flag = (
        " CFO already in place, capped finance gap."
        if enrichment.has_senior_finance_leader
        else ""
    )

    rationale = (
        f"{enrichment.stage} stage in '{enrichment.sector or 'unknown sector'}'. "
        f"Finance maturity {enrichment.finance_maturity_score}/5."
        f"{cfo_flag} Heuristic score — re-run with ANTHROPIC_API_KEY for a real rationale."
    )

    angle = (
        f"Lead investor {enrichment.lead_investor or 'unknown'} — "
        "check warm-intro path; verify finance team via LinkedIn URLs in the digest."
    )

    return CompanyScore(
        finance_gap_score=finance_gap,
        personal_fit_score=personal_fit,
        reachability_score=reachability,
        rationale=rationale,
        suggested_outreach_angle=angle,
    )
