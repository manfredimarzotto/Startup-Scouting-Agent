from scout.sources.rss import RSSSource


class TechCrunchSource(RSSSource):
    name = "techcrunch"
    url = "https://techcrunch.com/category/venture/feed/"
    require_funding_terms = True
