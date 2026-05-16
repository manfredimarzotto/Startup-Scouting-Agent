from scout.sources.rss import RSSSource


class SiftedSource(RSSSource):
    name = "sifted"
    url = "https://sifted.eu/feed"
    require_funding_terms = True
