"""Per-company enrichment via Claude Haiku, with offline heuristic fallback.

The fallback exists so the end-to-end mock run works in CI / without an API key.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import anthropic

from scout.enrichment.careers import CareersSignals
from scout.models import CompanyEnrichment, FundingEvent

_HAIKU = "claude-haiku-4-5"
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text()


def enrich_with_claude(
    event: FundingEvent,
    careers: CareersSignals | None = None,
    client: anthropic.Anthropic | None = None,
) -> CompanyEnrichment:
    """Call Haiku to enrich one funding event. Falls back to heuristic on any error."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return heuristic_enrich(event, careers)

    client = client or anthropic.Anthropic()
    system_prompt = _load_prompt("enrichment.md")

    user_blob = _format_inputs(event, careers)

    try:
        response = client.messages.parse(
            model=_HAIKU,
            max_tokens=1500,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_blob}],
            output_format=CompanyEnrichment,
        )
    except Exception:
        return heuristic_enrich(event, careers)

    return response.parsed_output or heuristic_enrich(event, careers)


def _format_inputs(event: FundingEvent, careers: CareersSignals | None) -> str:
    parts = [
        f"# Funding announcement",
        f"Source: {event.source}",
        f"URL: {event.source_url}",
        f"Title: {event.title}",
        f"Summary: {event.summary}",
        f"HQ hint from source: {event.raw_hq_hint or 'unknown'}",
    ]
    if careers:
        parts.append(f"\n# Careers page snippet ({careers.fetched_url})")
        parts.append(f"Detected finance-adjacent role mentions: {careers.finance_roles_found}")
        parts.append(f"Page text (truncated): {careers.raw_text_snippet}")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Heuristic fallback — used when no API key is set or the call fails.
# Keeps the mock run usable in CI without surprising opacity.
# ---------------------------------------------------------------------------

_STAGE_TERMS = {
    "series_a": re.compile(r"\bseries\s*a\b", re.IGNORECASE),
    "series_b": re.compile(r"\bseries\s*b\b", re.IGNORECASE),
    "series_c+": re.compile(r"\bseries\s*[c-z]\b", re.IGNORECASE),
    "seed": re.compile(r"\bseed\b", re.IGNORECASE),
    "pre-seed": re.compile(r"\bpre-?seed\b", re.IGNORECASE),
}

_AMOUNT = re.compile(
    r"(?:\$|€|£|USD|EUR|GBP)\s?(\d+(?:[\.,]\d+)?)\s*(m|million|bn|billion|k)?",
    re.IGNORECASE,
)


def heuristic_enrich(
    event: FundingEvent, careers: CareersSignals | None = None
) -> CompanyEnrichment:
    text = f"{event.title} {event.summary}"

    stage = "unknown"
    for s, rx in _STAGE_TERMS.items():
        if rx.search(text):
            stage = s
            break

    amount_usd = None
    m = _AMOUNT.search(text)
    if m:
        num = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        mult = {"m": 1_000_000, "million": 1_000_000, "bn": 1_000_000_000,
                "billion": 1_000_000_000, "k": 1_000}.get(unit, 1)
        amount_usd = int(num * mult)

    finance_roles = careers.finance_roles_found if careers else []
    has_cfo = None
    if finance_roles:
        senior_terms = ("CFO", "Chief Financial Officer", "Head of Finance",
                        "VP Finance", "Director of Finance")
        if any(any(t.lower() in role.lower() for t in senior_terms) for role in finance_roles):
            has_cfo = True

    maturity = 3
    if has_cfo:
        maturity = 4
    elif finance_roles:
        maturity = 2
    elif stage in ("series_a", "series_b") and not finance_roles:
        maturity = 1

    return CompanyEnrichment(
        company_name=event.company_name,
        hq_city=event.raw_hq_hint,
        hq_country=None,
        stage=stage,  # type: ignore[arg-type]
        round_amount_usd=amount_usd,
        sector=None,
        founder_background="unknown",
        has_senior_finance_leader=has_cfo,
        open_finance_roles=finance_roles,
        finance_maturity_score=maturity,
        notes="Enriched heuristically (no Claude API key or API call failed).",
    )
