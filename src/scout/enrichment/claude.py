"""Per-company enrichment via Claude Haiku, with offline heuristic fallback.

We use plain messages.create() and parse JSON client-side rather than the
structured-outputs API. Structured outputs rejected our 15-field schema as
"too complex" (run #6 log) — the prompted-JSON path bypasses that limit
entirely and is what most production Anthropic code does anyway.

The heuristic fallback exists so the end-to-end mock run works in CI / without
an API key.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

import anthropic
from pydantic import ValidationError

from scout.enrichment.careers import CareersSignals
from scout.models import CompanyEnrichment, FundingEvent

log = logging.getLogger("scout.enrichment.claude")

_HAIKU = "claude-haiku-4-5"
_PROMPTS_DIR = Path(__file__).resolve().parents[3] / "prompts"


def _load_prompt(name: str) -> str:
    return (_PROMPTS_DIR / name).read_text()


_JSON_OUTPUT_INSTRUCTION = """
Return ONLY a JSON object (no prose, no markdown fence) with these fields:
  company_name (string)
  hq_city (string or null)
  hq_country (string or null)
  stage (one of: pre-seed, seed, series_a, series_b, series_c+, unknown)
  round_amount_usd (integer or null)
  total_raised_usd (integer or null)
  lead_investor (string or null)
  other_investors (array of strings)
  sector (string or null)
  founder_background (one of: technical, commercial, mixed, unknown)
  has_senior_finance_leader (true, false, or null)
  senior_finance_leader_name (string or null)
  open_finance_roles (array of strings)
  finance_maturity_score (integer 1-5)
  notes (string or null)
"""


def enrich_with_claude(
    event: FundingEvent,
    careers: CareersSignals | None = None,
    client: anthropic.Anthropic | None = None,
) -> CompanyEnrichment:
    """Call Haiku to enrich one funding event. Falls back to heuristic on any error."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return heuristic_enrich(event, careers)

    client = client or anthropic.Anthropic(timeout=30.0)
    system_prompt = _load_prompt("enrichment.md") + _JSON_OUTPUT_INSTRUCTION

    user_blob = _format_inputs(event, careers)

    try:
        response = client.messages.create(
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
        )
    except anthropic.BadRequestError as exc:
        log.warning(
            "enrichment 400 for %s: %s", event.company_name, _short_error(exc)
        )
        return heuristic_enrich(event, careers)
    except Exception as exc:
        log.warning(
            "enrichment failed for %s: %s: %s",
            event.company_name,
            type(exc).__name__,
            _short_error(exc),
        )
        return heuristic_enrich(event, careers)

    text = "".join(b.text for b in response.content if b.type == "text")
    try:
        json_text = _extract_json(text)
        return CompanyEnrichment.model_validate_json(json_text)
    except (json.JSONDecodeError, ValidationError) as exc:
        log.warning(
            "enrichment JSON parse failed for %s: %s. Raw text: %s",
            event.company_name,
            type(exc).__name__,
            text[:200],
        )
        return heuristic_enrich(event, careers)


def _short_error(exc: Exception) -> str:
    """First line of the exception message, truncated. Keeps logs scannable."""
    msg = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
    return msg[:300]


def _extract_json(text: str) -> str:
    """Pull a JSON object out of the model's response.

    Tolerates: pure JSON, JSON in a ```json fence, JSON with prose around it.
    """
    text = text.strip()
    # Fenced code block (with or without "json" language hint)
    m = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text)
    if m:
        return m.group(1)
    # Bare JSON object — greedy match for the outermost braces
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        return text[start : end + 1]
    return text  # let json.loads fail with a useful message


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
