from datetime import datetime, timezone

from scout.models import CompanyEnrichment, FundingEvent
from scout.scoring.geo_filter import passes_geo_filter

ALLOWED = ["United Kingdom", "Sweden", "Germany", "Netherlands"]


def _event(name: str, hint: str | None) -> FundingEvent:
    return FundingEvent(
        source="mock",
        source_url="https://example.com/x",
        title=f"{name} raises something",
        summary="",
        company_name=name,
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        raw_hq_hint=hint,
    )


def test_country_match_passes():
    e = _event("Foo", None)
    enr = CompanyEnrichment(company_name="Foo", hq_country="Sweden")
    assert passes_geo_filter(e, enr, ALLOWED)


def test_city_to_country_passes():
    e = _event("Foo", "London")
    enr = CompanyEnrichment(company_name="Foo")
    assert passes_geo_filter(e, enr, ALLOWED)


def test_us_company_filtered_out():
    e = _event("Zenith", "San Francisco")
    enr = CompanyEnrichment(company_name="Zenith", hq_country="United States")
    assert not passes_geo_filter(e, enr, ALLOWED)


def test_unknown_location_filtered_out():
    """We drop unknown-geography companies rather than risk US noise."""
    e = _event("Foo", None)
    enr = CompanyEnrichment(company_name="Foo")
    assert not passes_geo_filter(e, enr, ALLOWED)
