"""UK/EU hard geo filter.

Companies outside the allowed_hq_countries list are dropped before scoring.
If geography is genuinely unknown after enrichment, we drop them — better to
miss a few than to fill the digest with US noise.
"""

from __future__ import annotations

from scout.models import CompanyEnrichment, FundingEvent

# City -> country map for the cases where enrichment leaves country empty.
_CITY_TO_COUNTRY = {
    "London": "United Kingdom",
    "Manchester": "United Kingdom",
    "Edinburgh": "United Kingdom",
    "Cambridge": "United Kingdom",
    "Bristol": "United Kingdom",
    "Dublin": "Ireland",
    "Paris": "France",
    "Lyon": "France",
    "Berlin": "Germany",
    "Munich": "Germany",
    "Hamburg": "Germany",
    "Amsterdam": "Netherlands",
    "Rotterdam": "Netherlands",
    "Stockholm": "Sweden",
    "Gothenburg": "Sweden",
    "Copenhagen": "Denmark",
    "Oslo": "Norway",
    "Helsinki": "Finland",
    "Madrid": "Spain",
    "Barcelona": "Spain",
    "Lisbon": "Portugal",
    "Milan": "Italy",
    "Rome": "Italy",
    "Zurich": "Switzerland",
    "Geneva": "Switzerland",
    "Vienna": "Austria",
    "Brussels": "Belgium",
    "Luxembourg": "Luxembourg",
    "Warsaw": "Poland",
    "Tallinn": "Estonia",
    "Vilnius": "Lithuania",
    "Riga": "Latvia",
    "Prague": "Czech Republic",
}


def passes_geo_filter(
    event: FundingEvent,
    enrichment: CompanyEnrichment,
    allowed_countries: list[str],
) -> bool:
    """Return True iff we have positive evidence the company HQ is in the allowed list."""
    allowed = {c.lower() for c in allowed_countries}

    if enrichment.hq_country and enrichment.hq_country.lower() in allowed:
        return True

    # Try mapping a city to a country.
    for city in filter(None, [enrichment.hq_city, event.raw_hq_hint]):
        country = _CITY_TO_COUNTRY.get(city)
        if country and country.lower() in allowed:
            return True

    return False
