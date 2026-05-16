"""Render scored companies into a daily markdown digest."""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path

import anthropic

from scout.models import ScoredCompany
from scout.pipeline import PipelineStats

_SONNET = "claude-sonnet-4-6"


def render_daily_digest(
    companies: list[ScoredCompany],
    stats: PipelineStats | None = None,
    top_n: int = 10,
) -> str:
    ordered = sorted(companies, key=lambda c: c.score.composite, reverse=True)[:top_n]

    today = date.today().isoformat()
    lines: list[str] = []
    lines.append(f"# Daily digest — {today}")
    lines.append("")
    lines.append(f"_Top {len(ordered)} of {len(companies)} surfaced after UK/EU filter._")
    lines.append("")

    if stats is not None:
        lines.extend(_render_stats_block(stats))

    if not ordered:
        lines.append("No companies passed the filters today.")
        return "\n".join(lines)

    for rank, c in enumerate(ordered, start=1):
        e = c.enrichment
        s = c.score
        cfo_tag = " *(CFO already in place — capped)*" if c.has_existing_cfo_flag else ""
        round_str = _format_amount(e.round_amount_usd)
        location = ", ".join(filter(None, [e.hq_city, e.hq_country])) or "location unknown"

        lines.append(
            f"## {rank}. {e.company_name} — composite {s.composite:.1f}{cfo_tag}"
        )
        lines.append("")
        lines.append(
            f"**Stage** {e.stage} | **Round** {round_str} | "
            f"**Lead** {e.lead_investor or '—'} | **HQ** {location}"
        )
        lines.append("")
        lines.append(
            f"**Scores** finance gap **{s.finance_gap_score}/10** · "
            f"personal fit **{s.personal_fit_score}/10** · "
            f"reachability **{s.reachability_score}/5**"
        )
        lines.append("")
        lines.append(s.rationale)
        lines.append("")
        lines.append(f"**Outreach angle:** {s.suggested_outreach_angle}")
        lines.append("")
        if e.open_finance_roles:
            lines.append(f"**Open finance-adjacent roles:** {', '.join(e.open_finance_roles)}")
            lines.append("")
        lines.append(
            f"**Links** · [Announcement]({c.event.source_url}) · "
            f"[LinkedIn company]({c.linkedin_search_urls.get('company_page', '#')}) · "
            f"[Finance team search]({c.linkedin_search_urls.get('finance_team_search', '#')}) · "
            f"[Google site:linkedin]({c.linkedin_search_urls.get('google_site_search', '#')})"
        )
        lines.append("")
        if e.notes:
            lines.append(f"> {e.notes}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def _render_stats_block(stats: PipelineStats) -> list[str]:
    """Compact diagnostic header so empty digests are debuggable at a glance."""
    out: list[str] = []
    out.append("<details><summary>Pipeline stats</summary>")
    out.append("")
    out.append("| source | http | raw | in window | funding-term | parsed | error |")
    out.append("|---|---:|---:|---:|---:|---:|---|")
    for name, s in stats.per_source.items():
        out.append(
            f"| {name} | {s.http_status or '—'} | {s.raw_entries} | {s.in_window} | "
            f"{s.funding_term_match} | {s.parsed_events} | {s.error or ''} |"
        )
    out.append("")
    out.append(
        f"**Funnel:** {stats.total_parsed} parsed → {stats.already_seen} already-seen "
        f"+ {stats.suppressed} suppressed + {stats.enriched} enriched → "
        f"{stats.geo_filter_passed} passed geo (dropped {stats.geo_filter_dropped}) → "
        f"{stats.scored} scored"
    )
    out.append("")
    out.append("</details>")
    out.append("")
    return out


def _format_amount(usd: int | None) -> str:
    if usd is None:
        return "undisclosed"
    if usd >= 1_000_000_000:
        return f"${usd / 1_000_000_000:.1f}B"
    if usd >= 1_000_000:
        return f"${usd / 1_000_000:.1f}M"
    return f"${usd:,}"


def render_weekly_synthesis(
    companies: list[ScoredCompany],
    client: anthropic.Anthropic | None = None,
) -> str:
    """Sonnet-powered synthesis. Falls back to a minimal list when no API key."""
    if not companies:
        return f"# Weekly synthesis — {date.today().isoformat()}\n\nNo companies this week."

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _fallback_weekly(companies)

    client = client or anthropic.Anthropic()
    prompt_path = Path(__file__).resolve().parents[3] / "prompts" / "weekly_synthesis.md"
    system_prompt = prompt_path.read_text()

    rows = "\n\n".join(
        f"- {c.enrichment.company_name} (composite {c.score.composite:.1f}, "
        f"stage {c.enrichment.stage}, lead {c.enrichment.lead_investor or '—'}, "
        f"sector {c.enrichment.sector or '—'}): {c.score.rationale}"
        for c in sorted(companies, key=lambda c: c.score.composite, reverse=True)
    )

    try:
        response = client.messages.create(
            model=_SONNET,
            max_tokens=4000,
            system=system_prompt,
            messages=[{"role": "user", "content": f"# Companies scored this week\n\n{rows}"}],
        )
    except Exception:
        return _fallback_weekly(companies)

    body = "\n".join(b.text for b in response.content if b.type == "text")
    return f"# Weekly synthesis — {date.today().isoformat()}\n\n{body}"


def _fallback_weekly(companies: list[ScoredCompany]) -> str:
    ordered = sorted(companies, key=lambda c: c.score.composite, reverse=True)
    lines = [f"# Weekly synthesis — {date.today().isoformat()}", "", "_API key missing — minimal list._", ""]
    for c in ordered[:10]:
        lines.append(
            f"- **{c.enrichment.company_name}** (composite {c.score.composite:.1f}) — "
            f"{c.enrichment.sector or 'sector unknown'}, lead {c.enrichment.lead_investor or '—'}"
        )
    return "\n".join(lines)
