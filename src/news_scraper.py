"""
News Scraper Module
Collects event-related news from configured RSS sources
"""

import feedparser
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from urllib.parse import urlparse, urlunparse
import json

from dateutil import parser as date_parser


class NewsScraper:
    """
    Scrapes configured news sources for event-category-specific articles
    """

    def __init__(self, config_path: str = "../config/settings.json"):
        """
        Initialize scraper with configuration

        Args:
            config_path: Path to settings.json configuration file
        """
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            # Use default config if file not found
            self.config = self._get_default_config()

        self.event_categories = self.config.get("event_categories", {})
        if not self.event_categories:
            self.event_categories = self._get_default_config().get("event_categories", {})

        self.keywords_by_category = {
            category: [keyword.lower() for keyword in category_config.get("keywords", [])]
            for category, category_config in self.event_categories.items()
        }
        self.breach_keywords = self.keywords_by_category.get("cybersecurity", [])

    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            "event_categories": {
                "cybersecurity": {
                    "enabled": True,
                    "keywords": [
                        "breach",
                        "data breach",
                        "security breach",
                        "hacked",
                        "hack",
                        "hackers",
                        "hacktivist",
                        "cyberattack",
                        "ransomware",
                        "exploit",
                        "vulnerability",
                        "compromised",
                        "attacked",
                        "attack",
                        "security incident",
                        "data exposure",
                        "credentials leaked",
                        "wiper",
                        "wipe",
                        "wiped",
                        "wiping",
                        "data wipe",
                        "data-wipe"
                    ]
                }
            },
            "news_sources": {
                "bleeping_computer": {
                    "enabled": True,
                    "url": "https://www.bleepingcomputer.com/feed/",
                    "event_category": "cybersecurity"
                },
                "krebs_on_security": {
                    "enabled": True,
                    "url": "https://krebsonsecurity.com/feed/",
                    "event_category": "cybersecurity"
                }
            },
            "scraping": {
                "timeout": 10,
                "max_results": 50,
                "max_results_per_source": 50,
                "hours_back": 24
            }
        }

    def _scraping_limits(self) -> Tuple[int, int]:
        """Return (max_results_per_source, timeout_seconds) from config."""
        scraping = self.config.get("scraping", {})
        max_n = int(
            scraping.get("max_results_per_source")
            or scraping.get("max_results")
            or 50
        )
        timeout = int(scraping.get("timeout") or 10)
        return max_n, timeout

    @staticmethod
    def _normalize_article_url(url: str) -> str:
        """Strip tracking query params and trailing slash for deduplication."""
        if not url:
            return ""
        try:
            p = urlparse(url.strip())
            path = p.path.rstrip("/") or "/"
            clean = urlunparse((p.scheme, p.netloc.lower(), path, "", "", ""))
            return clean
        except Exception:
            return url.strip().lower()

    def _entry_published_iso(self, entry: Dict) -> str:
        """Best-effort ISO 8601 timestamp for recency filtering."""
        parsed = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed:
            try:
                ts = timegm(parsed[:6])
                return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            except (TypeError, ValueError, OverflowError):
                pass
        raw = entry.get("published") or entry.get("updated")
        if raw:
            try:
                dt = date_parser.parse(raw)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.isoformat()
            except (ValueError, TypeError, OverflowError):
                pass
        return str(raw or "Unknown")

    def _is_category_enabled(self, event_category: str) -> bool:
        """Return True when a configured event category is enabled."""
        category_config = self.event_categories.get(event_category, {})
        if not category_config:
            return False
        return bool(category_config.get("enabled", False))

    def _get_category_keywords(self, event_category: str) -> List[str]:
        """Return lowercase keywords for an event category."""
        return self.keywords_by_category.get(event_category, [])

    def scrape_rss_feed(
        self,
        feed_url: str,
        source_name: str,
        event_category: str,
        keywords: List[str],
        max_entries: int,
    ) -> List[Dict]:
        """
        Scrape RSS feed for articles

        Args:
            feed_url: URL of RSS feed
            source_name: Name of news source
            event_category: Event category to assign to matching articles
            keywords: Keywords used to filter source content

        Returns:
            list: Articles containing category keywords
        """
        articles = []

        try:
            print(f"Fetching {source_name}...", end="")
            feed = feedparser.parse(feed_url)

            if not feed.entries:
                print(" No articles found")
                return articles

            entries = feed.entries[: max(1, max_entries)]

            # Look for breach-related articles
            for entry in entries:
                title = entry.get('title', '').lower()
                summary = entry.get('summary', '').lower()
                content = f"{title} {summary}".lower()

                if any(keyword in content for keyword in keywords):
                    published_iso = self._entry_published_iso(entry)
                    articles.append({
                        'source': source_name,
                        'event_category': event_category,
                        'title': entry.get('title', 'N/A'),
                        'link': entry.get('link', ''),
                        'published': published_iso,
                        'summary': entry.get('summary', ''),
                        'date_fetched': datetime.now().isoformat(),
                        'content_preview': content[:500]
                    })

            print(f" Found {len(articles)} relevant articles")
            return articles

        except Exception as e:
            print(f" Error fetching feed: {e}")
            return articles

    def scrape_all_sources(self) -> List[Dict]:
        """
        Scrape all configured news sources

        Returns:
            list: All breach-related articles from all sources
        """
        all_articles: List[Dict] = []
        seen_urls: set = set()

        print("\n" + "="*60)
        print("SCANNING NEWS SOURCES")
        print("="*60)

        max_entries, _ = self._scraping_limits()
        sources = self.config.get("news_sources", {})

        for source_name, source_config in sources.items():
            if not source_config.get("enabled", False):
                print(f"Skipping {source_name} (disabled)")
                continue

            event_category = source_config.get("event_category", "cybersecurity")
            if not self._is_category_enabled(event_category):
                print(
                    f"Skipping {source_name} "
                    f"(event_category '{event_category}' disabled)"
                )
                continue

            keywords = self._get_category_keywords(event_category)
            if not keywords:
                print(
                    f"Skipping {source_name} "
                    f"(event_category '{event_category}' has no keywords)"
                )
                continue

            feed_url = source_config.get("url")
            if feed_url:
                per_source = int(
                    source_config.get("max_results")
                    or source_config.get("max_results_per_source")
                    or max_entries
                )
                articles = self.scrape_rss_feed(
                    feed_url=feed_url,
                    source_name=source_name,
                    event_category=event_category,
                    keywords=keywords,
                    max_entries=per_source,
                )
                for a in articles:
                    key = self._normalize_article_url(a.get("link", ""))
                    if key and key in seen_urls:
                        continue
                    if key:
                        seen_urls.add(key)
                    all_articles.append(a)

        print(f"\n{'='*60}")
        print(f"Total articles found: {len(all_articles)}")
        print(f"{'='*60}\n")

        return all_articles

    def filter_recent_articles(self, articles: List[Dict], hours: int = 24) -> List[Dict]:
        """
        Filter articles to only those from recent period

        Args:
            articles: List of articles
            hours: Number of hours to look back

        Returns:
            list: Articles from the past N hours
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        recent = []

        for article in articles:
            pub_raw = article.get("published", "Unknown")
            try:
                pub_date = datetime.fromisoformat(
                    str(pub_raw).replace("Z", "+00:00")
                )
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=timezone.utc)
                if pub_date > cutoff_time:
                    recent.append(article)
            except (ValueError, AttributeError, TypeError):
                try:
                    pub_date = date_parser.parse(str(pub_raw))
                    if pub_date.tzinfo is None:
                        pub_date = pub_date.replace(tzinfo=timezone.utc)
                    if pub_date > cutoff_time:
                        recent.append(article)
                except (ValueError, TypeError, OverflowError):
                    # If date parsing fails, include the article anyway
                    recent.append(article)

        return recent

    def search_by_company(self, articles: List[Dict], company_name: str) -> List[Dict]:
        """
        Find articles mentioning a specific company

        Args:
            articles: List of articles to search
            company_name: Company name to search for

        Returns:
            list: Articles mentioning the company
        """
        results = []
        search_term = company_name.lower()

        for article in articles:
            content = (
                article.get('title', '').lower() +
                ' ' + article.get('summary', '').lower()
            )

            if search_term in content:
                results.append(article)

        return results

    def get_breach_stats(self, articles: List[Dict]) -> Dict:
        """
        Get statistics about breach articles

        Args:
            articles: List of articles

        Returns:
            dict: Statistics including count by source, keywords, etc
        """
        stats = {
            'total_articles': len(articles),
            'by_source': {},
            'breach_keywords_found': {}
        }

        # Count by source
        for article in articles:
            source = article.get('source', 'Unknown')
            stats['by_source'][source] = stats['by_source'].get(source, 0) + 1

        # Count keywords
        for article in articles:
            content = (
                article.get('title', '').lower() +
                ' ' + article.get('summary', '').lower()
            )

            keywords = self._get_category_keywords(article.get("event_category", "cybersecurity"))
            for keyword in keywords:
                if keyword in content:
                    stats['breach_keywords_found'][keyword] = \
                        stats['breach_keywords_found'].get(keyword, 0) + 1

        return stats

    def display_articles(self, articles: List[Dict], max_display: int = 10) -> None:
        """
        Display articles in readable format

        Args:
            articles: List of articles to display
            max_display: Maximum number to display
        """
        print(f"\nBREACH ARTICLES (showing {min(len(articles), max_display)} of {len(articles)})")
        print("="*80)

        for i, article in enumerate(articles[:max_display], 1):
            print(f"\n{i}. {article.get('title', 'No Title')}")
            print(f"   Source: {article.get('source', 'Unknown')}")
            print(f"   Published: {article.get('published', 'Unknown date')}")
            print(f"   Link: {article.get('link', 'No link')}")
            print(f"   Preview: {article.get('summary', 'No summary')[:200]}...")
            print("-"*80)


def main():
    """Test the scraper"""
    scraper = NewsScraper()

    # Scrape all sources
    articles = scraper.scrape_all_sources()

    # Display results
    if articles:
        scraper.display_articles(articles)

        # Show stats
        stats = scraper.get_breach_stats(articles)
        print("\nSTATISTICS")
        print("="*60)
        print(f"Total articles: {stats['total_articles']}")
        print(f"\nBy source:")
        for source, count in stats['by_source'].items():
            print(f"  {source}: {count}")
        print(f"\nTop keywords found:")
        sorted_keywords = sorted(
            stats['breach_keywords_found'].items(),
            key=lambda x: x[1],
            reverse=True
        )
        for keyword, count in sorted_keywords[:5]:
            print(f"  '{keyword}': {count}")
    else:
        print("No breach articles found.")


if __name__ == '__main__':
    main()
