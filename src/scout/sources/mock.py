"""Mock source for end-to-end testing without network calls."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from scout.models import FundingEvent


class MockSource:
    name = "mock"

    def __init__(self, fixture_path: Path | str | None = None) -> None:
        if fixture_path is None:
            fixture_path = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "mock_funding.json"
        self.fixture_path = Path(fixture_path)

    def fetch(self, lookback_days: int = 2) -> Iterable[FundingEvent]:
        data = json.loads(self.fixture_path.read_text())
        for row in data:
            yield FundingEvent(
                source=self.name,
                source_url=row["source_url"],
                title=row["title"],
                summary=row["summary"],
                company_name=row["company_name"],
                published_at=datetime.fromisoformat(row["published_at"]).replace(
                    tzinfo=timezone.utc
                ),
                raw_hq_hint=row.get("raw_hq_hint"),
            )
