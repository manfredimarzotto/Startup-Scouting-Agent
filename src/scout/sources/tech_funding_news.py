from scout.sources.rss import RSSSource


class TechFundingNewsSource(RSSSource):
    name = "tech_funding_news"
    url = "https://techfundingnews.com/feed/"
    # Whole site is funding-focused, so skip the keyword gate. Headlines
    # like "Series B announcement" lack the verb our regex looks for.
    require_funding_terms = False
