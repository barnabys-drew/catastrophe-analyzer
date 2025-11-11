"""
Entity Extractor Module
Extracts company names from breach articles and maps them to stock tickers
"""

import re
from typing import List, Dict, Optional, Tuple
import json


class EntityExtractor:
    """
    Extracts company entities from breach article text and validates ticker symbols
    """

    def __init__(self):
        """Initialize with common company patterns"""
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

        # Load known company-ticker mappings (extended list)
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
        }

        self.ticker_to_company = {v: k for k, v in self.company_to_ticker.items()}

    def extract_company_mentions(self, text: str) -> List[str]:
        """
        Extract potential company names from text

        Args:
            text: Article text to search

        Returns:
            list: Potential company names found
        """
        companies = []

        # Look for patterns like "Company Name Inc." or "Company Name Corp."
        patterns = [
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:Inc|Corp|Ltd|LLC)',
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:announced|said|reported)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, text)
            for match in matches:
                company_name = match.group(1).strip()
                if len(company_name) > 2:  # Filter out very short names
                    companies.append(company_name)

        return list(set(companies))  # Remove duplicates

    def get_ticker_for_company(self, company_name: str) -> Optional[str]:
        """
        Get stock ticker for a company name

        Args:
            company_name: Company name to look up

        Returns:
            str: Stock ticker symbol or None
        """
        normalized_name = company_name.lower().strip()

        # Direct match
        if normalized_name in self.company_to_ticker:
            return self.company_to_ticker[normalized_name]

        # Partial match (for company name variations)
        for known_name, ticker in self.company_to_ticker.items():
            if known_name in normalized_name or normalized_name in known_name:
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

    def extract_and_map_companies(self, article: Dict) -> Dict:
        """
        Extract companies from an article and map to tickers

        Args:
            article: Article dict with title and summary

        Returns:
            dict: Article with extracted companies and tickers
        """
        # Combine title and summary for searching
        full_text = article.get('title', '') + ' ' + article.get('summary', '')

        # Extract company mentions
        companies = self.extract_company_mentions(full_text)

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
            'extracted_companies': companies,
            'mapped_entities': mapped_entities,
            'has_publicly_traded': len(mapped_entities) > 0
        }

    def batch_extract(self, articles: List[Dict]) -> List[Dict]:
        """
        Extract entities from multiple articles

        Args:
            articles: List of article dictionaries

        Returns:
            list: Articles with extracted entities
        """
        results = []
        for article in articles:
            results.append(self.extract_and_map_companies(article))
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

    def display_extraction_results(self, articles: List[Dict]) -> None:
        """
        Display extraction results in readable format

        Args:
            articles: Articles with extracted entities
        """
        print("\nEXTRACTED ENTITIES")
        print("="*80)

        publicly_traded_count = sum(1 for a in articles if a.get('has_publicly_traded'))
        print(f"Articles with publicly traded companies: {publicly_traded_count}/{len(articles)}\n")

        # Show most mentioned companies
        most_mentioned = self.get_most_mentioned_companies(articles)
        if most_mentioned:
            print("Most Mentioned Companies:")
            print("-"*40)
            for i, (company, ticker, count) in enumerate(most_mentioned, 1):
                print(f"{i}. {company} ({ticker}): {count} mentions")
        else:
            print("No publicly traded companies found in articles")

        # Show articles with entities
        print("\n" + "="*80)
        for i, article in enumerate(articles[:5], 1):
            if article.get('mapped_entities'):
                print(f"\n{i}. {article.get('title')}")
                print(f"   Companies found:")
                for entity in article.get('mapped_entities', []):
                    print(f"     - {entity.get('company')} ({entity.get('ticker')})")


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
