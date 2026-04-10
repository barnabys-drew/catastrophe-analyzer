"""
Catastrophe Analyzer — shock events in the news, ticker linkage, and equity signal heuristics.

Implementation today spans multiple `event_category` lanes (cybersecurity, clinical/regulatory,
product safety, fraud/accounting/enforcement, supply chain disruption, financial distress,
dilutive financing, M&A/corporate action, leadership scandal, positive earnings catalyst);
see docs/EVENT_CATEGORIES_AND_IMPACT.md.
"""

__version__ = "1.0.0"
__author__ = "Stock Manager Team"

from .news_scraper import NewsScraper
from .entity_extractor import EntityExtractor
from .stock_analyzer import StockAnalyzer
from .signal_generator import SignalGenerator
from .database_manager import DatabaseManager

__all__ = [
    'NewsScraper',
    'EntityExtractor',
    'StockAnalyzer',
    'SignalGenerator',
    'DatabaseManager',
]
