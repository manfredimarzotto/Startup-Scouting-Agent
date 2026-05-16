"""Generate LinkedIn search URLs the user clicks through manually.

We do not scrape LinkedIn. URLs go in the digest so the candidate can verify
finance team composition by hand. This avoids ToS issues entirely.
"""

from __future__ import annotations

from urllib.parse import quote_plus


def linkedin_search_urls(company_name: str) -> dict[str, str]:
    """Returns labelled search URLs for the candidate to click through."""
    company_q = quote_plus(company_name)
    finance_titles = quote_plus(
        f'"{company_name}" ("CFO" OR "Head of Finance" OR "VP Finance" OR "Strategic Finance")'
    )
    return {
        "company_page": f"https://www.linkedin.com/search/results/companies/?keywords={company_q}",
        "finance_team_search": (
            f"https://www.linkedin.com/search/results/people/?keywords={finance_titles}"
        ),
        "google_site_search": (
            f"https://www.google.com/search?q=site%3Alinkedin.com%2Fin+%22{company_q}%22+"
            "%28CFO+OR+%22Head+of+Finance%22+OR+%22VP+Finance%22%29"
        ),
    }
