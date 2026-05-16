from scout.sources.rss import RSSSource


class TechEuSource(RSSSource):
    name = "tech_eu"
    url = "https://tech.eu/category/funding/feed/"
    require_funding_terms = False
