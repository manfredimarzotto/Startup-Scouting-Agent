"""Generate a static HTML dashboard from scout.db.

Single self-contained file with vanilla JS — no build step, no framework.
Published to docs/index.html and served via GitHub Pages.
"""

from __future__ import annotations

import html
import json
from datetime import date, datetime, timezone
from pathlib import Path

from scout.models import ScoredCompany
from scout.storage import ScoutDB


def render_dashboard(db: ScoutDB) -> str:
    """Pull every scored company out of the DB and render the dashboard HTML."""
    companies = db.recent(days=10_000)  # effectively "all"

    rows = [_to_row(c) for c in companies]
    last_updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return _TEMPLATE.format(
        title="Startup Scout — finance opportunities",
        last_updated=html.escape(last_updated),
        total=len(rows),
        rows_json=json.dumps(rows),
    )


def _to_row(c: ScoredCompany) -> dict:
    e = c.enrichment
    s = c.score
    return {
        "company": e.company_name,
        "composite": round(s.composite, 1),
        "finance_gap": s.finance_gap_score,
        "personal_fit": s.personal_fit_score,
        "reachability": s.reachability_score,
        "stage": e.stage,
        "round_usd": e.round_amount_usd,
        "hq_city": e.hq_city or "",
        "hq_country": e.hq_country or "",
        "sector": e.sector or "",
        "lead_investor": e.lead_investor or "",
        "founder_background": e.founder_background,
        "has_cfo": bool(c.has_existing_cfo_flag),
        "rationale": s.rationale,
        "outreach_angle": s.suggested_outreach_angle,
        "announcement_url": c.event.source_url,
        "linkedin_company": c.linkedin_search_urls.get("company_page", ""),
        "linkedin_finance": c.linkedin_search_urls.get("finance_team_search", ""),
        "source": c.event.source,
        "announced_date": c.event.published_at.date().isoformat(),
    }


# Self-contained HTML. No external deps. Dark theme, sticky header, client-side
# filter + sort. Renders thousands of rows fine.
_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  :root {{
    --bg: #0d1117;
    --surface: #161b22;
    --border: #30363d;
    --text: #e6edf3;
    --muted: #7d8590;
    --accent: #58a6ff;
    --good: #3fb950;
    --warn: #d29922;
    --bad: #f85149;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 32px; font: 14px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg); color: var(--text);
  }}
  h1 {{ margin: 0 0 4px; font-size: 22px; font-weight: 600; }}
  .subtitle {{ color: var(--muted); margin-bottom: 24px; font-size: 13px; }}
  .controls {{
    display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;
    position: sticky; top: 0; padding: 16px 0; background: var(--bg); z-index: 10;
  }}
  input, select {{
    background: var(--surface); border: 1px solid var(--border); color: var(--text);
    padding: 8px 12px; border-radius: 6px; font-size: 13px;
  }}
  input[type=search] {{ width: 280px; }}
  input:focus, select:focus {{ outline: none; border-color: var(--accent); }}
  .count {{ color: var(--muted); padding: 8px 0; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ text-align: left; padding: 10px 12px; border-bottom: 1px solid var(--border); vertical-align: top; }}
  th {{
    background: var(--surface); cursor: pointer; user-select: none; font-weight: 600;
    position: sticky; top: 64px; z-index: 5;
  }}
  th:hover {{ color: var(--accent); }}
  th.sort-asc::after {{ content: " \\2191"; color: var(--accent); }}
  th.sort-desc::after {{ content: " \\2193"; color: var(--accent); }}
  tr:hover td {{ background: var(--surface); }}
  td.composite {{ font-weight: 600; font-size: 15px; text-align: right; font-variant-numeric: tabular-nums; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .pill {{
    display: inline-block; padding: 2px 8px; border-radius: 10px;
    font-size: 11px; font-weight: 600; text-transform: uppercase;
  }}
  .pill-series_a {{ background: #1f6feb33; color: #79c0ff; }}
  .pill-series_b {{ background: #a371f733; color: #d2a8ff; }}
  .pill-seed     {{ background: #3fb95033; color: #7ce38b; }}
  .pill-pre-seed {{ background: #d2992233; color: #e3b341; }}
  .pill-series_c\\+ {{ background: #f8514933; color: #ff7b72; }}
  .pill-unknown  {{ background: #30363d; color: var(--muted); }}
  .pill-cfo      {{ background: #f8514922; color: #ff7b72; margin-left: 6px; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  .rationale {{ color: var(--muted); max-width: 480px; font-size: 12px; }}
  details {{ margin-top: 6px; }}
  summary {{ cursor: pointer; color: var(--accent); font-size: 12px; }}
  .empty {{ padding: 40px; text-align: center; color: var(--muted); }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">{total} companies tracked · last updated {last_updated} · <a href="https://github.com/manfredimarzotto/Startup-Scouting-Agent/tree/main/digests">browse daily digests →</a></div>

<div class="controls">
  <input type="search" id="search" placeholder="Search company, sector, investor, rationale…">
  <select id="stage">
    <option value="">All stages</option>
    <option value="series_a">Series A</option>
    <option value="series_b">Series B</option>
    <option value="seed">Seed</option>
    <option value="pre-seed">Pre-seed</option>
    <option value="series_c+">Series C+</option>
    <option value="unknown">Unknown</option>
  </select>
  <select id="min-score">
    <option value="0">All scores</option>
    <option value="5">≥ 5.0</option>
    <option value="6">≥ 6.0</option>
    <option value="7">≥ 7.0</option>
    <option value="8">≥ 8.0</option>
  </select>
  <select id="cfo">
    <option value="">CFO: any</option>
    <option value="no">No senior finance leader</option>
    <option value="yes">Has CFO (capped)</option>
  </select>
</div>

<div class="count" id="count"></div>

<table id="grid">
  <thead>
    <tr>
      <th data-key="composite" data-num="1">Composite</th>
      <th data-key="company">Company</th>
      <th data-key="stage">Stage</th>
      <th data-key="hq_country">HQ</th>
      <th data-key="lead_investor">Lead investor</th>
      <th data-key="finance_gap" data-num="1">Fin gap</th>
      <th data-key="personal_fit" data-num="1">Fit</th>
      <th data-key="reachability" data-num="1">Reach</th>
      <th>Rationale</th>
      <th data-key="announced_date">Announced</th>
    </tr>
  </thead>
  <tbody id="rows"></tbody>
</table>

<div class="empty" id="empty" style="display:none">No companies match the current filters.</div>

<script>
const DATA = {rows_json};

const $ = (id) => document.getElementById(id);
const search = $("search"), stage = $("stage"), minScore = $("min-score"), cfo = $("cfo");
const tbody = $("rows"), countEl = $("count"), emptyEl = $("empty");

let sortKey = "composite", sortDir = "desc";

function fmtUsd(n) {{
  if (!n) return "—";
  if (n >= 1e9) return "$" + (n / 1e9).toFixed(1) + "B";
  if (n >= 1e6) return "$" + (n / 1e6).toFixed(1) + "M";
  return "$" + n.toLocaleString();
}}

function escapeHtml(s) {{
  return (s || "").replace(/[&<>"']/g, c => ({{
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  }}[c]));
}}

function rowHtml(r) {{
  const stagePill = `<span class="pill pill-${{r.stage}}">${{r.stage.replace("_", " ")}}</span>`;
  const cfoPill = r.has_cfo ? `<span class="pill pill-cfo">CFO present</span>` : "";
  const hq = [r.hq_city, r.hq_country].filter(Boolean).join(", ") || "—";
  const lead = r.lead_investor || "—";
  const round = r.round_usd ? ` · ${{fmtUsd(r.round_usd)}}` : "";
  const sector = r.sector ? `<div style="color:var(--muted); font-size:12px">${{escapeHtml(r.sector)}}${{round}}</div>` : (round ? `<div style="color:var(--muted); font-size:12px">${{round.slice(3)}}</div>` : "");
  const links = `<div style="margin-top:6px"><a href="${{escapeHtml(r.announcement_url)}}" target="_blank">announcement</a> · <a href="${{escapeHtml(r.linkedin_company)}}" target="_blank">LinkedIn</a> · <a href="${{escapeHtml(r.linkedin_finance)}}" target="_blank">finance team</a></div>`;

  return `<tr>
    <td class="composite">${{r.composite.toFixed(1)}}</td>
    <td><strong>${{escapeHtml(r.company)}}</strong>${{cfoPill}}${{sector}}${{links}}</td>
    <td>${{stagePill}}</td>
    <td>${{escapeHtml(hq)}}</td>
    <td>${{escapeHtml(lead)}}</td>
    <td class="num">${{r.finance_gap}}/10</td>
    <td class="num">${{r.personal_fit}}/10</td>
    <td class="num">${{r.reachability}}/5</td>
    <td class="rationale">
      ${{escapeHtml(r.rationale)}}
      <details><summary>outreach angle</summary>${{escapeHtml(r.outreach_angle)}}</details>
    </td>
    <td>${{r.announced_date}}<div style="color:var(--muted); font-size:11px">${{escapeHtml(r.source)}}</div></td>
  </tr>`;
}}

function applyFilters() {{
  const q = search.value.toLowerCase().trim();
  const stageVal = stage.value;
  const minS = parseFloat(minScore.value);
  const cfoVal = cfo.value;

  let rows = DATA.filter(r => {{
    if (stageVal && r.stage !== stageVal) return false;
    if (r.composite < minS) return false;
    if (cfoVal === "yes" && !r.has_cfo) return false;
    if (cfoVal === "no" && r.has_cfo) return false;
    if (q) {{
      const hay = [r.company, r.sector, r.lead_investor, r.rationale, r.hq_city, r.hq_country].join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }}
    return true;
  }});

  rows.sort((a, b) => {{
    const va = a[sortKey], vb = b[sortKey];
    if (typeof va === "number") return sortDir === "asc" ? va - vb : vb - va;
    return sortDir === "asc" ? String(va).localeCompare(String(vb)) : String(vb).localeCompare(String(va));
  }});

  tbody.innerHTML = rows.map(rowHtml).join("");
  countEl.textContent = `${{rows.length}} of ${{DATA.length}} companies`;
  emptyEl.style.display = rows.length === 0 ? "block" : "none";

  document.querySelectorAll("th[data-key]").forEach(th => {{
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.key === sortKey) th.classList.add("sort-" + sortDir);
  }});
}}

document.querySelectorAll("th[data-key]").forEach(th => {{
  th.addEventListener("click", () => {{
    const key = th.dataset.key;
    if (sortKey === key) {{
      sortDir = sortDir === "asc" ? "desc" : "asc";
    }} else {{
      sortKey = key;
      sortDir = th.dataset.num ? "desc" : "asc";
    }}
    applyFilters();
  }});
}});

[search, stage, minScore, cfo].forEach(el => el.addEventListener("input", applyFilters));
applyFilters();
</script>
</body>
</html>
"""
