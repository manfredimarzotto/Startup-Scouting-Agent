from scout.sources.rss import RSSSource


class EUStartupsSource(RSSSource):
    name = "eu_startups"
    # The category-feed URL pattern (/category/funding/feed/) 404s. Main feed
    # works; the funding-term regex filters it down to fundraise headlines.
    url = "https://www.eu-startups.com/feed/"
    require_funding_terms = True
