"""
Breach Analyzer Package
Cyber security breach detection and stock analysis
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
