"""Dynamic company profile generation - NO HARDCODING.

All URLs are discovered dynamically from the website structure.
"""

from dataclasses import dataclass, field
from typing import List
from urllib.parse import urljoin, urlparse


@dataclass
class CompanyProfile:
    company_id: str
    careers_urls: List[str] = field(default_factory=list)
    blog_feeds: List[str] = field(default_factory=list)
    blog_indexes: List[str] = field(default_factory=list)
    max_articles: int = 50  # Reasonable default for comprehensive extraction
    max_jobs_pages: int = 5  # Allow multiple careers pages

    def ensure_defaults(self, base_url: str) -> None:
        """Populate sensible defaults dynamically - NO HARDCODING."""
        # Generate common careers URL patterns
        if not self.careers_urls:
            self.careers_urls = [
                urljoin(base_url, "/careers"),
                urljoin(base_url, "/jobs"),
                urljoin(base_url, "/company/careers"),
                urljoin(base_url, "/careers/jobs"),
                urljoin(base_url, "/open-positions"),
                urljoin(base_url, "/join-us"),
            ]

        # Generate common blog/news URL patterns
        if not self.blog_indexes:
            self.blog_indexes = [
                urljoin(base_url, "/blog"),
                urljoin(base_url, "/news"),
                urljoin(base_url, "/press"),
                urljoin(base_url, "/articles"),
                urljoin(base_url, "/updates"),
                urljoin(base_url, "/insights"),
            ]

        # Generate common RSS feed URL patterns
        if not self.blog_feeds:
            # Common RSS feed locations
            base_paths = ["/blog", "/news", "/press", "/feed", ""]
            feed_names = ["rss.xml", "feed.xml", "rss", "feed", "atom.xml", "index.xml"]
            
            for base_path in base_paths:
                for feed_name in feed_names:
                    feed_url = urljoin(base_url, f"{base_path}/{feed_name}")
                    if feed_url not in self.blog_feeds:
                        self.blog_feeds.append(feed_url)


def get_company_profile(company_id: str, base_url: str) -> CompanyProfile:
    """Return dynamically generated company profile - NO HARDCODING.
    
    All URLs are generated from common patterns, not hardcoded per company.
    The scraper will discover and use the actual URLs that exist.
    """
    profile = CompanyProfile(company_id=company_id)
    profile.ensure_defaults(base_url)
    return profile


