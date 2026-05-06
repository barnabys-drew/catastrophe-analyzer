"""
News Scraper Module
Collects event-related news from configured RSS sources
"""

import os
import time
import socket
from calendar import timegm
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from urllib.parse import urlparse, urlunparse
import json
from email.utils import parsedate_to_datetime

from text_match import keyword_in_text
from config_loader import load_settings

try:
    from dateutil import parser as date_parser
except ImportError:
    class _DateParserFallback:
        @staticmethod
        def parse(value: str):
            try:
                return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError):
                return parsedate_to_datetime(str(value))

    date_parser = _DateParserFallback()

try:
    import feedparser
except ImportError:
    class _FeedParserFallback:
        @staticmethod
        def parse(*args, **kwargs):
            raise ImportError("feedparser is required for RSS parsing")

    feedparser = _FeedParserFallback()


class NewsScraper:
    """
    Scrapes configured news sources for event-category-specific articles
    """

    def __init__(self, config_path: str = "../config/settings.json", settings: Dict | None = None):
        """
        Initialize scraper with configuration

        Args:
            config_path: Path to settings.json configuration file
        """
        self.config = settings if settings is not None else load_settings(self._resolve_config_path(config_path))

        self.event_categories = self.config.get("event_categories", {})
        if not self.event_categories:
            self.event_categories = self._get_default_config().get("event_categories", {})

        self.keywords_by_category = {
            category: [keyword.lower() for keyword in category_config.get("keywords", [])]
            for category, category_config in self.event_categories.items()
        }
        self.breach_keywords = self.keywords_by_category.get("cybersecurity", [])

        scraping = self.config.get("scraping", {}) or {}
        ua = (os.environ.get("CATASTROPHE_HTTP_USER_AGENT") or "").strip() or (
            str(scraping.get("http_user_agent") or "").strip()
        )
        if not ua:
            ua = (
                "CatastropheAnalyzer/1.0 (+https://www.sec.gov/about/developer-resources; "
                "set scraping.http_user_agent in settings.json or CATASTROPHE_HTTP_USER_AGENT)"
            )
        self._feed_request_headers = {
            "User-Agent": ua[:500],
            "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
        }
        self._retry_on_failure = bool(scraping.get("retry_on_failure", True))
        try:
            self._max_retries = max(0, int(scraping.get("max_retries", 0)))
        except (TypeError, ValueError):
            self._max_retries = 0
        try:
            self._retry_backoff_seconds = max(0.0, float(scraping.get("retry_backoff_seconds", 1.0)))
        except (TypeError, ValueError):
            self._retry_backoff_seconds = 1.0
        self._drop_unparseable_published = bool(scraping.get("drop_unparseable_published", True))
        try:
            self._max_article_age_hours = float(scraping.get("max_article_age_hours", 0))
        except (TypeError, ValueError):
            self._max_article_age_hours = 0.0
        self._title_blocklist = [
            p.upper() for p in scraping.get("title_blocklist_patterns", []) if p
        ]

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

    @staticmethod
    def _resolve_config_path(config_path: str) -> str:
        """Resolve relative config path from this module location."""
        if os.path.isabs(config_path):
            return config_path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(base_dir, config_path))

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

        max_attempts = 1 + self._max_retries if self._retry_on_failure else 1
        print(f"Fetching {source_name}...", end="")

        # Get timeout from config
        _, timeout_seconds = self._scraping_limits()

        for attempt in range(1, max_attempts + 1):
            try:
                # Set socket timeout to prevent indefinite hangs
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout_seconds)
                try:
                    feed = feedparser.parse(feed_url, request_headers=self._feed_request_headers)
                finally:
                    socket.setdefaulttimeout(old_timeout)
                if getattr(feed, "bozo", False) and getattr(feed, "bozo_exception", None):
                    raise RuntimeError(str(feed.bozo_exception))

                if not feed.entries:
                    print(" No articles found")
                    return articles

                entries = feed.entries[: max(1, max_entries)]

                # Look for breach-related articles
                for entry in entries:
                    title = entry.get('title', '').lower()
                    summary = entry.get('summary', '').lower()
                    content = f"{title} {summary}".lower()

                    if any(keyword_in_text(keyword, content) for keyword in keywords):
                        # Fix 1: drop plaintiff-firm boilerplate alerts by title
                        raw_title = entry.get('title', '')
                        title_upper = raw_title.upper()
                        if self._title_blocklist and any(pat in title_upper for pat in self._title_blocklist):
                            continue

                        # Fix 2: require at least one high-severity keyword for gated categories
                        cat_config = self.event_categories.get(event_category, {})
                        if cat_config.get("high_severity_required"):
                            sev_kws = [k.lower() for k in cat_config.get("high_severity_keywords", [])]
                            if sev_kws and not any(keyword_in_text(kw, content) for kw in sev_kws):
                                continue

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

                if attempt > 1:
                    print(f" recovered on attempt {attempt}; found {len(articles)} relevant articles")
                else:
                    print(f" Found {len(articles)} relevant articles")
                return articles
            except Exception as e:
                should_retry = attempt < max_attempts
                if should_retry:
                    print(f" attempt {attempt}/{max_attempts} failed ({e}); retrying...", end="")
                    if self._retry_backoff_seconds > 0:
                        time.sleep(self._retry_backoff_seconds * attempt)
                    continue
                print(f" Error fetching feed: {e}")
                return articles

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
        effective_hours = float(max(1, int(hours)))
        if self._max_article_age_hours > 0:
            effective_hours = min(effective_hours, self._max_article_age_hours)
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=effective_hours)
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
                    if not self._drop_unparseable_published:
                        recent.append(article)

        return recent

    # ------------------------------------------------------------------
    # Full-article body enrichment
    # ------------------------------------------------------------------

    @staticmethod
    def _needs_body_fetch(article: Dict) -> bool:
        """
        True when RSS content is likely too thin for entity extraction:
        - Google News URL (always a redirect with a truncated snippet)
        - Summary under 250 chars (company name probably not present)
        - Government/regulatory source (SEC, FDA, DOJ, CPSC use structured one-liners)
        """
        url = article.get("link", "") or ""
        summary = article.get("summary", "") or ""
        source = (article.get("source", "") or "").lower()
        if "news.google.com" in url:
            return True
        if len(summary.strip()) < 250:
            return True
        gov_prefixes = ("sec_", "fda_", "doj_", "cpsc_", "usda_", "justice_")
        if any(source.startswith(p) for p in gov_prefixes):
            return True
        return False

    def fetch_article_body(self, url: str, timeout: int = 8, max_chars: int = 3000) -> str:
        """
        Fetch and extract plain text from a news article URL.
        Follows redirects (handles Google News redirect URLs).
        Returns up to max_chars of text, or empty string on any failure.
        Never raises.
        """
        try:
            import requests as _requests
            from bs4 import BeautifulSoup
        except ImportError:
            return ""

        try:
            resp = _requests.get(
                url,
                headers={
                    "User-Agent": self._feed_request_headers.get("User-Agent", ""),
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                },
                timeout=timeout,
                allow_redirects=True,
            )
            if resp.status_code != 200:
                return ""
            soup = BeautifulSoup(resp.content, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
                tag.decompose()
            container = soup.find("article") or soup.find("main") or soup.find("body")
            if not container:
                return ""
            text = container.get_text(separator=" ", strip=True)
            # Collapse runs of whitespace
            import re as _re
            text = _re.sub(r"\s{2,}", " ", text)
            return text[:max_chars].strip()
        except Exception:
            return ""

    def enrich_articles_with_body(
        self,
        articles: List[Dict],
        max_fetches: int = 30,
        fetch_delay_seconds: float = 0.5,
    ) -> List[Dict]:
        """
        Selectively fetch full article bodies for articles whose RSS content is
        likely too thin to contain a company name for entity extraction.
        Adds a 'body' key to qualifying article dicts in-place.

        max_fetches caps total HTTP requests per cycle to avoid latency blow-up.
        fetch_delay_seconds inserts a polite pause between requests.
        """
        fetched = 0
        for article in articles:
            if fetched >= max_fetches:
                break
            if article.get("body"):
                continue
            if not self._needs_body_fetch(article):
                continue
            url = article.get("link", "")
            if not url:
                continue
            body = self.fetch_article_body(url)
            if body:
                article["body"] = body
                fetched += 1
                if fetch_delay_seconds > 0 and fetched < max_fetches:
                    time.sleep(fetch_delay_seconds)
        if fetched:
            print(f"[body_fetch] enriched {fetched}/{len(articles)} articles with full article text")
        return articles

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
                if keyword_in_text(keyword, content):
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
