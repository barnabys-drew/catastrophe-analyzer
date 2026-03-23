"""
Entity Extractor Module
Extracts company names from breach articles and maps them to stock tickers.
Supports the full public company set via dynamic lookup (Yahoo Finance search).
"""

import re
import os
from typing import List, Dict, Optional, Tuple
import json

try:
    import requests
except ImportError:
    requests = None


class EntityExtractor:
    """
    Extracts company entities from breach article text and validates ticker symbols.
    Uses a pre-seeded cache plus on-demand Yahoo Finance search for any public company.
    """

    YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
    USER_AGENT = "Mozilla/5.0 (compatible; CatastropheAnalyzer/1.0)"

    # Yahoo / search "exchange" values that indicate US listing (major venues).
    _US_EXCHANGES = frozenset({
        "NMS", "NAS", "NGM", "NCM", "NYQ", "NYM", "PCX", "ASE", "BTS", "CBOE",
        "NASDAQ", "NYSE", "NYSEARCA", "AMEX", "NYSE MKT", "OTC", "PNK", "BATS",
    })

    # Never treat as a company for ticker lookup (countries, generic headline words).
    _ENTITY_BLOCKLIST = frozenset({
        "iran", "iraq", "china", "russia", "india", "israel", "ukraine", "brazil",
        "korea", "japan", "france", "germany", "canada", "mexico", "europe", "nato",
        "things", "internet", "department", "huge", "manager", "services", "actions",
        "geopolitical", "identity", "emergency", "medtech", "magento", "federal", "feds",
        "botnets", "android", "signal", "github", "azure",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "winter", "summer", "spring", "fall", "government", "security", "national",
        "american", "european", "asian", "global", "public", "private", "critical",
        "firm", "maker", "device", "medical", "attack", "attacks", "phishing",
    })

    _BLOCKLIST_PHRASES = frozenset({
        "medtech firm", "medical device", "device maker", "identity manager",
        "git hub", "e stores",
    })

    # Minimum length for fuzzy substring match against seed map (avoids "ge" in "geopolitical" -> GE).
    _MIN_PARTIAL_NAME_LEN = 5
    _TRAILING_TRIM_WORDS = frozenset({
        "for", "in", "on", "after", "amid", "as", "with", "from", "into", "at",
    })

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with common company patterns and optional config."""
        if config_path is None:
            # Default: config next to repo root when running from src/
            _dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(_dir, "..", "config", "settings.json")
        self.company_patterns = [
            r'(?:Inc|Inc\.|Corp|Corp\.|Company|Co\.|Ltd|LLC|CORPORATION|CORPORATION\.)',
            r'(?:\(.*?\))',  # Parenthetical company identifiers
        ]

        # Common cybersecurity-related entity keywords
        self.entity_keywords = [
            'hospital', 'bank', 'university', 'school', 'government',
            'airline', 'retail', 'manufacturing', 'healthcare',
            'telecom', 'technology', 'software', 'financial',
            'energy', 'oil', 'gas', 'insurance', 'services'
        ]

        # Config: dynamic lookup and cache (defaults)
        self._config = self._load_config(config_path)
        self._us_listed_only = self._config.get("us_listed_equities_only", True)
        self._use_dynamic_lookup = self._config.get("use_dynamic_lookup", True)
        self._cache_lookups = self._config.get("cache_lookups", True)
        self._cache_file = self._config.get("cache_file")  # optional path

        # Pre-seeded cache (fast path); also stores results from dynamic lookups
        self.company_to_ticker = {
            # Large tech companies
            'apple': 'AAPL',
            'microsoft': 'MSFT',
            'google': 'GOOGL',
            'alphabet': 'GOOGL',
            'amazon': 'AMZN',
            'meta': 'META',
            'facebook': 'META',
            'twitter': 'TWTR',
            'x corporation': 'TWTR',
            'nvidia': 'NVDA',
            'amd': 'AMD',
            'intel': 'INTC',
            'cisco': 'CSCO',
            'ibm': 'IBM',
            'oracle': 'ORCL',
            'salesforce': 'CRM',
            'adobe': 'ADBE',
            'zoom': 'ZM',
            'slack': 'SLACK',
            'crowdstrike': 'CRWD',
            'palo alto': 'PANW',
            'fortinet': 'FTNT',
            'cloudflare': 'NET',

            # Financial and Services
            'jpmorgan': 'JPM',
            'j.p. morgan': 'JPM',
            'bank of america': 'BAC',
            'citigroup': 'C',
            'wells fargo': 'WFC',
            'goldman sachs': 'GS',
            'morgan stanley': 'MS',
            'capital one': 'COF',
            'american express': 'AXP',
            'visa': 'V',
            'mastercard': 'MA',
            'paypal': 'PYPL',
            'square': 'SQ',
            'stripe': 'UNKNOWN',
            'coinbase': 'COIN',

            # Healthcare and Pharma
            'johnson & johnson': 'JNJ',
            'pfizer': 'PFE',
            'moderna': 'MRNA',
            'merck': 'MRK',
            'eli lilly': 'LLY',
            'astrazeneca': 'AZN',
            'unitedhealth': 'UNH',
            'cvs health': 'CVS',
            'walgreens': 'WBA',
            'anthem': 'ANTM',

            # Retail and Consumer
            'walmart': 'WMT',
            'target': 'TGT',
            'costco': 'COST',
            'amazon': 'AMZN',
            'ebay': 'EBAY',
            'home depot': 'HD',
            'lowes': 'LOW',
            'best buy': 'BBY',
            'nike': 'NKE',
            'adidas': 'ADDYY',

            # Telecommunications
            'at&t': 'T',
            'verizon': 'VZ',
            'comcast': 'CMCSA',
            't-mobile': 'TMUS',
            'charter': 'CHTR',

            # Airlines and Transportation
            'delta': 'DAL',
            'united': 'UAL',
            'american': 'AAL',
            'southwest': 'LUV',

            # Energy
            'exxon': 'XOM',
            'chevron': 'CVX',
            'shell': 'SHEL',
            'bp': 'BP',

            # Industrial/Manufacturing
            'boeing': 'BA',
            'lockheed martin': 'LMT',
            'ge': 'GE',
            'general electric': 'GE',
            'stryker': 'SYK',
            'stryker corporation': 'SYK',
        }

        # In-memory lookup cache (dynamic lookups added here when cache_lookups is True)
        self._lookup_cache: Dict[str, Optional[str]] = {}
        if self._cache_file and os.path.isfile(self._cache_file):
            self._load_lookup_cache()

        self.ticker_to_company = {v: k for k, v in self.company_to_ticker.items()}

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load entity_extraction section from config file."""
        defaults = {
            "use_dynamic_lookup": True,
            "cache_lookups": True,
            "cache_file": None,
            "us_listed_equities_only": True,
        }
        if not config_path:
            return defaults
        try:
            with open(config_path, "r") as f:
                full = json.load(f)
            section = full.get("entity_extraction", {})
            return {**defaults, **section}
        except (FileNotFoundError, json.JSONDecodeError):
            return defaults

    def _load_lookup_cache(self) -> None:
        """Load persisted lookup cache from cache_file into cache and company_to_ticker."""
        if not self._cache_file:
            return
        try:
            with open(self._cache_file, "r") as f:
                data = json.load(f)
            for k, v in data.items():
                if v and v != "UNKNOWN":
                    if self._us_listed_only and not self._is_us_primary_symbol(str(v)):
                        continue
                    key = k.lower()
                    self._lookup_cache[key] = v
                    self.company_to_ticker[key] = v
            self.ticker_to_company = {v: k for k, v in self.company_to_ticker.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_lookup_cache(self) -> None:
        """Persist lookup cache to cache_file (only dynamic entries beyond initial seed)."""
        if not self._cache_file:
            return
        try:
            with open(self._cache_file, "w") as f:
                json.dump(self._lookup_cache, f, indent=2)
        except OSError:
            pass

    @staticmethod
    def _is_us_primary_symbol(symbol: str) -> bool:
        """Reject foreign listings (e.g. RANI3.SA); allow optional class suffix BRK.A."""
        if not symbol:
            return False
        s = symbol.upper().strip()
        if re.search(
            r"\.(SA|L|DE|F|VI|HK|KS|T|AX|TO|PA|MI|AS|SW|ST|BR|MX|NS|BO)$",
            s,
        ):
            return False
        if "." in s:
            return bool(re.match(r"^[A-Z]{1,5}\.[A-Z]$", s))
        return bool(re.match(r"^[A-Z]{1,5}$", s))

    def _yahoo_quote_is_us_equity(self, quote: Dict) -> bool:
        if (quote.get("quoteType") or "").upper() != "EQUITY":
            return False
        sym = (quote.get("symbol") or "").strip().upper()
        if not self._is_us_primary_symbol(sym):
            return False
        if not self._us_listed_only:
            return True
        ex = (quote.get("exchange") or "").strip().upper()
        if not ex:
            return True
        if ex in self._US_EXCHANGES:
            return True
        if "NASDAQ" in ex or "NYSE" in ex or "AMEX" in ex or "BATS" in ex:
            return True
        return False

    def _dynamic_lookup_company(self, company_name: str) -> Optional[str]:
        """
        Resolve company name to ticker via Yahoo Finance search API.
        When us_listed_equities_only: first match that is US-listed equity only.
        """
        if not requests:
            return None
        name = (company_name or "").strip()
        if not name or len(name) < 2:
            return None
        try:
            resp = requests.get(
                self.YAHOO_SEARCH_URL,
                params={"q": name, "quotes_count": 12},
                headers={"User-Agent": self.USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError, KeyError):
            return None
        quotes = data.get("quotes", [])
        for q in quotes:
            if not self._yahoo_quote_is_us_equity(q):
                continue
            sym = (q.get("symbol") or "").strip()
            if sym:
                return sym.upper()
        return None

    def extract_company_mentions(self, text: str, event_category: Optional[str] = None) -> List[str]:
        """
        Extract potential company names from text.
        Includes standalone names (e.g. "Stryker was hacked") and Inc/Corp patterns.
        """
        companies = []

        # Patterns like "Company Name Inc." or "Company Name Corp." (limit to 3 words to avoid sentence capture)
        # Limit to 1-2 word company names to avoid capturing generic phrases
        # (e.g. "Medtech Firm Stryker" -> should ideally yield "Stryker").
        patterns = [
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:Inc|Corp|Ltd|LLC)\.?",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:announced|said|reported|confirmed|disclosed)\s+",
            # Standalone company name before breach-related verbs: "Stryker was hacked"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:was|is|has been|gets|got)\s+(?:hacked|breached|compromised|attacked|hit)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:says|confirmed|reported|announced|disclosed)\s+",
            # After breach context: "breach at Stryker", "attack on Microsoft"
            r"(?:breach|attack|incident|ransomware|hack)\s+(?:at|on|hits?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})",
        ]
        if event_category == "clinical_regulatory_binary":
            patterns.extend(
                [
                    # "Company announced phase 3/topline/FDA decision ..."
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:announced|reports?|reported|posted|disclosed)\s+"
                    r"(?:phase\s*(?:2|ii|3|iii)|topline|top-line|fda|clinical|trial)",
                    # "FDA issues CRL to Company"
                    r"(?:fda|food and drug administration)\s+(?:issues?|issued|sent)\s+"
                    r"(?:a\s+)?(?:complete response letter|crl)\s+to\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                    # "Company receives FDA approval"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:receives?|received|wins?|won|gets?|got)\s+"
                    r"(?:fda approval|approval|complete response letter|crl|clinical hold)",
                ]
            )

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Handle different group positions (some patterns capture company in group 1)
                company_name = (match.group(1) or "").strip()
                if len(company_name) > 2 and company_name not in ("The", "The Company", "A"):
                    companies.append(company_name)

        # Single capitalized word (4+ chars) in breach context: "Stryker hacked" or "breach at Stryker"
        min_len = self._config.get("min_company_name_length", 2)
        breach_words = (
            "breach hacked hack hackers hacktivist cyberattack ransomware exploit vulnerability "
            "compromised attacked attack incident disclosed announced wiper wipe wiped data-wiping data wipe"
        )
        clinical_words = (
            "fda approval complete response letter crl clinical hold trial hold phase 2 phase 3 "
            "phase ii phase iii topline top-line endpoint adverse event safety signal pdufa nda bla"
        )
        context_words = breach_words
        if event_category == "clinical_regulatory_binary":
            context_words = f"{breach_words} {clinical_words}"
        stop_words = (
            "the and said have this that with from when company medical device maker firm "
            "medical medtech device maker monday tuesday wednesday thursday friday saturday "
            "sunday security week breach city state country region european internet union claim "
            "center management iran iraq china russia india israel brazil canada japan france "
            "germany korea ukraine nato federal feds department identity emergency geopolitical "
            "magento actions manager services things internet huge botnets phishing android "
            "signal github azure monitor magento identity things department fda phase trial topline"
        ).split()
        text_lower = text.lower()
        for m in re.finditer(r"\b([A-Z][a-z]{3,})\b", text):
            name = m.group(1)
            if name.lower() in stop_words:
                continue
            # Must appear near a breach-related word (same sentence or within ~40 chars)
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text_lower[start:end]
            if any(bw in snippet for bw in context_words.split()):
                companies.append(name)

        return self._clean_company_mentions(companies)

    def _clean_company_mentions(self, raw_companies: List[str]) -> List[str]:
        """Normalize and dedupe extracted company mentions."""
        cleaned: List[str] = []
        for raw in raw_companies:
            name = re.sub(r"\s+", " ", (raw or "").strip(" ,.;:-")).strip()
            if not name:
                continue
            parts = name.split()
            while parts and parts[-1].lower() in self._TRAILING_TRIM_WORDS:
                parts = parts[:-1]
            if not parts:
                continue
            name = " ".join(parts)
            if len(name) < 3:
                continue
            if name.lower() in self._ENTITY_BLOCKLIST:
                continue
            cleaned.append(name)

        # Keep longer/more-specific names first (e.g. "Sarepta Therapeutics" over "Sarepta").
        unique = sorted(set(cleaned), key=lambda x: (-len(x), x))
        kept: List[str] = []
        for candidate in unique:
            padded = f" {candidate.lower()} "
            if any(padded in f" {k.lower()} " for k in kept):
                continue
            kept.append(candidate)
        return kept

    def get_ticker_for_company(self, company_name: str) -> Optional[str]:
        """
        Get stock ticker for a company name.
        Uses cache/static map first, then dynamic Yahoo Finance search for full public set.
        """
        normalized_name = company_name.lower().strip()
        if not normalized_name:
            return None
        if normalized_name in self._ENTITY_BLOCKLIST:
            return None
        if normalized_name in self._BLOCKLIST_PHRASES:
            return None

        # Fast path: direct match
        if normalized_name in self.company_to_ticker:
            ticker = self.company_to_ticker[normalized_name]
            if ticker == "UNKNOWN":
                return None
            if self._us_listed_only and not self._is_us_primary_symbol(ticker):
                return None
            return ticker

        # Partial match (longer seed keys, word-boundary style — avoids "united" in "unitedhealth")
        padded = f" {normalized_name} "
        for known_name, ticker in self.company_to_ticker.items():
            if len(known_name) < self._MIN_PARTIAL_NAME_LEN:
                continue
            in_padded = f" {known_name} " in padded
            at_start = normalized_name.startswith(known_name + " ")
            at_end = normalized_name.endswith(" " + known_name)
            # Longer canonical name contains query as a distinct word (e.g. query "apple" vs key "apple inc")
            longer = len(known_name) > len(normalized_name) and (
                known_name.startswith(normalized_name + " ")
                or known_name.endswith(" " + normalized_name)
                or f" {normalized_name} " in f" {known_name} "
            )
            if not (in_padded or at_start or at_end or longer):
                continue
            if ticker == "UNKNOWN":
                continue
            if self._us_listed_only and not self._is_us_primary_symbol(ticker):
                continue
            return ticker

        # Dynamic lookup: full public company set via Yahoo Finance
        if self._use_dynamic_lookup and requests:
            ticker = self._dynamic_lookup_company(company_name)
            if ticker and (not self._us_listed_only or self._is_us_primary_symbol(ticker)):
                if self._cache_lookups:
                    self.company_to_ticker[normalized_name] = ticker
                    self._lookup_cache[normalized_name] = ticker
                    self.ticker_to_company[ticker] = normalized_name
                    if self._cache_file:
                        self._save_lookup_cache()
                return ticker

        return None

    def get_company_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Get company name for a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            str: Company name or None
        """
        ticker_upper = ticker.upper().strip()
        return self.ticker_to_company.get(ticker_upper)

    def extract_and_map_companies(self, article: Dict, event_category: Optional[str] = None) -> Dict:
        """
        Extract companies from an article and map to tickers

        Args:
            article: Article dict with title and summary

        Returns:
            dict: Article with extracted companies and tickers
        """
        resolved_event_category = event_category or article.get("event_category")

        # Combine title and summary for searching
        full_text = article.get('title', '') + ' ' + article.get('summary', '')

        # Extract company mentions
        companies = self.extract_company_mentions(full_text, event_category=resolved_event_category)

        # Map to tickers
        mapped_entities = []
        for company in companies:
            ticker = self.get_ticker_for_company(company)
            if ticker and ticker != 'UNKNOWN':
                mapped_entities.append({
                    'company': company,
                    'ticker': ticker,
                    'confidence': 'high' if company in full_text else 'medium'
                })

        return {
            **article,
            'event_category': resolved_event_category,
            'extracted_companies': companies,
            'mapped_entities': mapped_entities,
            'has_publicly_traded': len(mapped_entities) > 0
        }

    def batch_extract(self, articles: List[Dict], event_category: Optional[str] = None) -> List[Dict]:
        """
        Extract entities from multiple articles

        Args:
            articles: List of article dictionaries

        Returns:
            list: Articles with extracted entities
        """
        results = []
        for article in articles:
            article_event_category = event_category or article.get("event_category")
            results.append(self.extract_and_map_companies(article, event_category=article_event_category))
        return results

    def get_ticker_mentions(self, articles: List[Dict]) -> Dict[str, int]:
        """
        Get count of how many times each ticker appears in articles

        Args:
            articles: Processed articles with mapped entities

        Returns:
            dict: Ticker -> mention count
        """
        ticker_counts = {}

        for article in articles:
            for entity in article.get('mapped_entities', []):
                ticker = entity.get('ticker')
                if ticker:
                    ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

        return ticker_counts

    def get_most_mentioned_companies(self, articles: List[Dict], limit: int = 10) -> List[Tuple[str, str, int]]:
        """
        Get most frequently mentioned companies in articles

        Args:
            articles: Processed articles with mapped entities
            limit: Number of results to return

        Returns:
            list: Tuples of (company_name, ticker, mention_count)
        """
        ticker_counts = self.get_ticker_mentions(articles)

        results = []
        for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
            company_name = self.get_company_for_ticker(ticker)
            results.append((company_name or ticker, ticker, count))

        return results

    def unlisted_mentions(self, article: Dict) -> List[str]:
        """Names extracted from text that did not resolve to a mapped public ticker."""
        mapped_lower = {m.get("company", "").strip().lower() for m in article.get("mapped_entities", [])}
        out: List[str] = []
        for c in article.get("extracted_companies") or []:
            key = (c or "").strip().lower()
            if key and key not in mapped_lower:
                out.append(c)
        return out

    def display_scan_preview(self, articles: List[Dict], max_articles: int = 15) -> None:
        """
        After a news scan: show each article with public tickers and other extracted names.
        """
        print("\nArticles with extracted names (public tickers + other mentions)")
        print("-" * 80)
        n_pub = sum(1 for a in articles if a.get("has_publicly_traded"))
        print(
            f"Summary: {len(articles)} articles — {n_pub} with at least one US-listed ticker, "
            f"{len(articles) - n_pub} with none from extraction.\n"
        )
        for i, article in enumerate(articles[:max_articles], 1):
            print(f"{i}. {article.get('title', 'No title')}")
            print(f"   Source: {article.get('source')}  |  category: {article.get('event_category', 'n/a')}")
            mapped = article.get("mapped_entities") or []
            if mapped:
                pub = ", ".join(f"{m.get('company')} ({m.get('ticker')})" for m in mapped)
                print(f"   US-listed (NYSE/Nasdaq-style): {pub}")
            else:
                print("   US-listed (NYSE/Nasdaq-style): (none from this headline)")
            other = self.unlisted_mentions(article)
            if other:
                print(f"   Other mentions (no listed ticker in our map): {', '.join(other)}")
            elif not mapped:
                print("   Other mentions: (none extracted)")
            print()
        if len(articles) > max_articles:
            print(f"… and {len(articles) - max_articles} more articles (run full analysis to process all).\n")

    def display_extraction_results(self, articles: List[Dict]) -> None:
        """
        Display extraction results in readable format

        Args:
            articles: Articles with extracted entities
        """
        print("\nEXTRACTED ENTITIES")
        print("="*80)

        publicly_traded_count = sum(1 for a in articles if a.get('has_publicly_traded'))
        print(f"Articles with US-listed tickers: {publicly_traded_count}/{len(articles)}\n")

        # Show most mentioned companies
        most_mentioned = self.get_most_mentioned_companies(articles)
        if most_mentioned:
            print("Most Mentioned Companies:")
            print("-"*40)
            for i, (company, ticker, count) in enumerate(most_mentioned, 1):
                print(f"{i}. {company} ({ticker}): {count} mentions")
        else:
            print("No US-listed tickers found in articles")

        # Show articles with entities
        print("\n" + "="*80)
        for i, article in enumerate(articles[:5], 1):
            print(f"\n{i}. {article.get('title')}")
            if article.get('mapped_entities'):
                print("   Listed (ticker):")
                for entity in article.get('mapped_entities', []):
                    print(f"     - {entity.get('company')} ({entity.get('ticker')})")
            else:
                print("   Listed (ticker): (none)")
            other = self.unlisted_mentions(article)
            if other:
                print(f"   Other mentions: {', '.join(other)}")


def main():
    """Test the extractor"""
    extractor = EntityExtractor()

    # Test articles
    test_articles = [
        {
            'title': 'Apple Inc. Announces Major Security Breach',
            'summary': 'Apple has confirmed a data breach affecting customer accounts...',
            'source': 'test',
            'link': 'test.com'
        },
        {
            'title': 'Microsoft Corporation Responds to Cyberattack',
            'summary': 'Microsoft stated that the attack was contained quickly...',
            'source': 'test',
            'link': 'test.com'
        },
        {
            'title': 'JPMorgan Chase Investigates Incident',
            'summary': 'The bank confirmed a security incident affecting...',
            'source': 'test',
            'link': 'test.com'
        },
    ]

    # Extract entities
    processed = extractor.batch_extract(test_articles)

    # Display results
    extractor.display_extraction_results(processed)


if __name__ == '__main__':
    main()
