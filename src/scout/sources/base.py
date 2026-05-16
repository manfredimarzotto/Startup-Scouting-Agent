"""Source protocol. New sources implement fetch() and return FundingEvents."""

from __future__ import annotations

from typing import Iterable, Protocol

from scout.models import FundingEvent


class Source(Protocol):
    name: str

    def fetch(self, lookback_days: int = 2) -> Iterable[FundingEvent]: ...
