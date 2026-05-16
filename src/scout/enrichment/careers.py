"""Fetch and lightly parse a company's careers page for finance-adjacent roles.

Best-effort: tries a handful of common URL patterns, returns whatever it finds.
Failures are silent — Claude enrichment handles the company without this signal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

import httpx
from selectolax.parser import HTMLParser

_FINANCE_ROLE_PATTERNS = [
    r"\bCFO\b",
    r"\bChief Financial Officer\b",
    r"\bHead of Finance\b",
    r"\bVP,? Finance\b",
    r"\bDirector of Finance\b",
    r"\bStrategic Finance\b",
    r"\bFP&A\b",
    r"\bFinance Manager\b",
    r"\bFinance Lead\b",
    r"\bFinance Director\b",
    r"\bBizOps\b",
    r"\bBusiness Operations\b",
    r"\bRevOps\b",
    r"\bRevenue Operations\b",
    r"\bChief of Staff\b",
    r"\bFounder['’]s Associate\b",
]

_CAREER_URL_CANDIDATES = [
    "/careers",
    "/jobs",
    "/work-with-us",
    "/join-us",
    "/about/careers",
]


@dataclass
class CareersSignals:
    fetched_url: str | None
    finance_roles_found: list[str]
    raw_text_snippet: str


def fetch_careers_signals(company_homepage: str | None, timeout: float = 6.0) -> CareersSignals | None:
    """Try to find finance-adjacent roles on the company's careers page.

    Returns None if no careers URL is discoverable or the page is empty.
    """
    if not company_homepage:
        return None

    base = company_homepage.rstrip("/")
    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers={"User-Agent": "startup-scouting-agent/0.1 (research)"},
    ) as client:
        for path in _CAREER_URL_CANDIDATES:
            try:
                resp = client.get(base + path)
            except httpx.HTTPError:
                continue
            if resp.status_code != 200 or not resp.text:
                continue
            text = _visible_text(resp.text)
            roles = _find_finance_roles(text)
            if text or roles:
                return CareersSignals(
                    fetched_url=str(resp.url),
                    finance_roles_found=roles,
                    raw_text_snippet=text[:4000],
                )
    return None


def _visible_text(html: str) -> str:
    tree = HTMLParser(html)
    for tag in tree.css("script, style, noscript"):
        tag.decompose()
    body = tree.body
    text = body.text(separator=" ", strip=True) if body else tree.text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def _find_finance_roles(text: str) -> list[str]:
    hits: list[str] = []
    for pattern in _FINANCE_ROLE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            hits.append(pattern.strip("\\b").replace("\\", ""))
    # Dedup while preserving order.
    seen = set()
    out = []
    for h in hits:
        key = h.lower()
        if key not in seen:
            seen.add(key)
            out.append(h)
    return out
