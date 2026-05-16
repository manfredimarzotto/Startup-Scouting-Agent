"""SQLite-backed state. Two jobs: idempotency (don't re-enrich the same event) and
caching of scored output so weekly synthesis can pull a window cheaply."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scout.models import ScoredCompany

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scored_companies (
    fingerprint TEXT PRIMARY KEY,
    company_name TEXT NOT NULL,
    composite REAL NOT NULL,
    scored_at TEXT NOT NULL,
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_scored_at ON scored_companies(scored_at);
CREATE INDEX IF NOT EXISTS idx_company_name ON scored_companies(company_name);
"""


class ScoutDB:
    def __init__(self, path: str | Path = "./scout.db") -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def has_seen(self, fingerprint: str) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM scored_companies WHERE fingerprint = ?",
            (fingerprint,),
        )
        return cur.fetchone() is not None

    def save(self, sc: ScoredCompany) -> None:
        self.conn.execute(
            """
            INSERT OR REPLACE INTO scored_companies
              (fingerprint, company_name, composite, scored_at, payload_json)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                sc.event.fingerprint(),
                sc.enrichment.company_name,
                sc.score.composite,
                datetime.now(timezone.utc).isoformat(),
                sc.model_dump_json(),
            ),
        )
        self.conn.commit()

    def recent(self, days: int = 7) -> list[ScoredCompany]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self.conn.execute(
            "SELECT payload_json FROM scored_companies WHERE scored_at >= ? ORDER BY composite DESC",
            (cutoff,),
        )
        return [ScoredCompany.model_validate(json.loads(row[0])) for row in cur.fetchall()]

    def close(self) -> None:
        self.conn.close()
