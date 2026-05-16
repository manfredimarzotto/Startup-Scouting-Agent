"""Source adapters. Each source yields FundingEvent objects."""

from scout.sources.base import Source
from scout.sources.eu_startups import EUStartupsSource
from scout.sources.mock import MockSource
from scout.sources.sifted import SiftedSource
from scout.sources.tech_eu import TechEuSource
from scout.sources.techcrunch import TechCrunchSource
from scout.sources.uktn import UKTNSource

LIVE_SOURCES: list[type[Source]] = [
    TechCrunchSource,
    SiftedSource,
    EUStartupsSource,
    TechEuSource,
    UKTNSource,
]

__all__ = [
    "Source",
    "LIVE_SOURCES",
    "MockSource",
    "TechCrunchSource",
    "SiftedSource",
    "EUStartupsSource",
    "TechEuSource",
    "UKTNSource",
]
