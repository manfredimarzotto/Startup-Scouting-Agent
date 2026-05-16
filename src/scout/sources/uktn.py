from scout.sources.rss import RSSSource


class UKTNSource(RSSSource):
    name = "uktn"
    url = "https://www.uktech.news/feed"
    require_funding_terms = True
