from scout.sources.rss import RSSSource


class EUStartupsSource(RSSSource):
    name = "eu_startups"
    url = "https://www.eu-startups.com/category/funding/feed/"
    # Category feed is funding-only; skip the keyword gate so we don't drop entries
    # whose titles use unusual phrasing.
    require_funding_terms = False
