"""Command-line entry point.

Examples:
    scout run-mock                   # end-to-end on fixture data, no API key needed
    scout run                        # daily run against live RSS sources
    scout synth                      # weekly synthesis over the last 7 days
    scout dashboard                  # regenerate docs/index.html from scout.db
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path

from scout.digest import render_daily_digest, render_dashboard, render_weekly_synthesis
from scout.outreach.angle import load_pipeline_suppression
from scout.pipeline import default_live_sources, load_fit_profile, run, run_mock
from scout.storage import ScoutDB

DEFAULT_FIT_PROFILE = "config/fit_profile.yaml"
DEFAULT_PIPELINE_FILE = "config/companies_in_pipeline.yaml"


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    parser = argparse.ArgumentParser(prog="scout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="Run the daily pipeline against live sources.")
    p_run.add_argument("--lookback-days", type=int, default=int(os.environ.get("SCOUT_LOOKBACK_DAYS", "2")))
    p_run.add_argument("--fit-profile", default=DEFAULT_FIT_PROFILE)
    p_run.add_argument("--pipeline-file", default=DEFAULT_PIPELINE_FILE)
    p_run.add_argument("--top-n", type=int, default=10)

    p_mock = sub.add_parser("run-mock", help="End-to-end run on fixture data. Used by CI.")
    p_mock.add_argument("--fit-profile", default=DEFAULT_FIT_PROFILE)
    p_mock.add_argument("--pipeline-file", default=DEFAULT_PIPELINE_FILE)
    p_mock.add_argument("--top-n", type=int, default=10)

    p_synth = sub.add_parser("synth", help="Weekly synthesis (Sonnet) over the last N days.")
    p_synth.add_argument("--days", type=int, default=7)

    sub.add_parser("dashboard", help="Regenerate docs/index.html from scout.db.")

    args = parser.parse_args(argv)

    db_path = os.environ.get("SCOUT_DB_PATH", "./scout.db")
    digest_dir = Path(os.environ.get("SCOUT_DIGEST_DIR", "./digests"))
    digest_dir.mkdir(parents=True, exist_ok=True)
    db = ScoutDB(db_path)

    if args.cmd in ("run", "run-mock"):
        fit_profile = load_fit_profile(args.fit_profile)
        suppression = load_pipeline_suppression(args.pipeline_file)

        if args.cmd == "run":
            result = run(
                sources=default_live_sources(),
                fit_profile=fit_profile,
                db=db,
                suppression=suppression,
                lookback_days=args.lookback_days,
            )
        else:
            result = run_mock(fit_profile=fit_profile, db=db, suppression=suppression)

        digest = render_daily_digest(result.scored, stats=result.stats, top_n=args.top_n)
        out_path = digest_dir / f"{date.today().isoformat()}.md"
        out_path.write_text(digest)
        print(
            f"Scored {len(result.scored)} companies "
            f"(parsed {result.stats.total_parsed} from {len(result.stats.per_source)} sources, "
            f"dropped {result.stats.geo_filter_dropped} on geo). "
            f"Digest written to {out_path}"
        )
        return 0

    if args.cmd == "synth":
        recent = db.recent(days=args.days)
        synth = render_weekly_synthesis(recent)
        out_path = digest_dir / f"weekly-{date.today().isoformat()}.md"
        out_path.write_text(synth)
        print(f"Synthesis over {len(recent)} companies written to {out_path}")
        return 0

    if args.cmd == "dashboard":
        docs_dir = Path("./docs")
        docs_dir.mkdir(parents=True, exist_ok=True)
        html_out = render_dashboard(db)
        out_path = docs_dir / "index.html"
        out_path.write_text(html_out)
        print(f"Dashboard regenerated at {out_path}")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
