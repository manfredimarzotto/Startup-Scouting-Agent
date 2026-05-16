"""Spot-check name extraction against headlines the live run actually hit."""

from scout.sources.rss import RSSSource


def _name(title: str) -> str | None:
    return RSSSource().extract_company_name(title, "")


def test_simple_name():
    assert _name("Lovable raises $25M Series A led by Accel") == "Lovable"


def test_possessive_geo_prefix():
    # The headline that surfaced Eighteen48 in the first real run.
    assert _name("London's Eighteen48 raises €175M first close") == "Eighteen48"


def test_based_geo_prefix():
    assert _name("Berlin-based BuildMate secures £8M seed") == "BuildMate"


def test_descriptor_prefix():
    assert _name("Construction startup CropWise raises €12M Series A") == "CropWise"


def test_widened_verbs():
    assert _name("Acme bags €5M seed round") == "Acme"
    assert _name("Acme wins €5M from Index") == "Acme"
    assert _name("Acme completes Series B funding") == "Acme"
    assert _name("Acme grabs $10M from Atomico") == "Acme"


def test_multi_word_name():
    assert _name("Tech Funding News raises $5M Series A") == "Tech Funding News"


def test_fallback_returns_first_capitalized_phrase():
    # Doesn't match any strict pattern, but we still want SOMETHING so Haiku
    # can correct it downstream.
    result = _name("Apricot raised funding from Sequoia, sources say")
    assert result is not None
    assert "Apricot" in result
