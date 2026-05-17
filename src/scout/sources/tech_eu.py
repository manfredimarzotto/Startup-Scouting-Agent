from scout.sources.rss import RSSSource


class TechEuSource(RSSSource):
    name = "tech_eu"
    # The category-feed URL pattern (/category/funding/feed/) 404s. Main feed
    # works; the funding-term regex filters it down to fundraise headlines.
    url = "https://tech.eu/feed/"
    require_funding_terms = True
