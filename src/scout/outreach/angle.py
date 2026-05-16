"""Pipeline suppression. The scoring prompt produces the per-company outreach angle;
this module just loads the user-maintained suppression list."""

from __future__ import annotations

from pathlib import Path

import yaml


def load_pipeline_suppression(path: str | Path) -> set[str]:
    """Return the set of normalized company names to suppress from the digest."""
    p = Path(path)
    if not p.exists():
        return set()
    data = yaml.safe_load(p.read_text()) or {}
    entries = data.get("pipeline") or []
    return {_normalize(e["name"]) for e in entries if e.get("name")}


def _normalize(name: str) -> str:
    return name.strip().lower()


def is_suppressed(company_name: str, suppression: set[str]) -> bool:
    return _normalize(company_name) in suppression
