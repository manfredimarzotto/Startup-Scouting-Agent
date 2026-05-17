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


def test_blacklist_drops_garbage_from_real_run():
    # Names that actually surfaced in run #5 and wasted Haiku calls.
    assert _name("Marketing X raises $5M Series A") is None
    assert _name("Two startups raised funding this week") is None
    assert _name("HTGF Family Day connected startups with VCs") is None
    # "-backed" headlines are editorial framing, not fundraises
    assert _name("Sheryl Sandberg-backed startup raises $50M") is None
    # VCs / big tech mentioned in fundraise context shouldn't be extracted
    # as the fundraise subject
    assert _name("Lightrock leads $20M round in green tech") is None


def test_blacklist_keeps_real_names_with_generic_words():
    # Stripe, Notion etc. are common words but ARE real company names.
    # Make sure the blacklist isn't over-aggressive on multi-word names.
    assert _name("Stripe Climate raises $50M Series B") == "Stripe Climate"


def test_all_caps_short_acronyms_dropped():
    # "UK raises £5M" would extract "UK" — clearly a country code, not a co.
    assert _name("UK raises £5M for AI safety institute") is None
