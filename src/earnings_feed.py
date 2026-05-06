"""Earnings surprise detection for swing trade signals."""
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import requests
from dataclasses import dataclass

log = logging.getLogger("earnings_feed")


@dataclass
class EarningsSurprise:
    """Earnings surprise event."""
    ticker: str
    company_name: str
    report_date: str  # YYYY-MM-DD when earnings were reported
    eps_estimate: float
    eps_actual: float
    eps_surprise_pct: float  # (actual - estimate) / estimate * 100
    revenue_estimate: float
    revenue_actual: float
    revenue_surprise_pct: float
    guidance_change: Optional[str]  # "raised", "lowered", "maintained"
    analyst_rating_change: Optional[str]  # "upgrade", "downgrade", "reiterate"
    source: str = "earnings_surprise"

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "report_date": self.report_date,
            "eps_estimate": self.eps_estimate,
            "eps_actual": self.eps_actual,
            "eps_surprise_pct": self.eps_surprise_pct,
            "revenue_estimate": self.revenue_estimate,
            "revenue_actual": self.revenue_actual,
            "revenue_surprise_pct": self.revenue_surprise_pct,
            "guidance_change": self.guidance_change,
            "analyst_rating_change": self.analyst_rating_change,
            "source": self.source,
        }


class EarningsFeed:
    """Fetch earnings surprises and guidance from data providers.

    Current limitation: Public APIs for real-time earnings are either limited (yfinance)
    or paid (Zacks, TradingView). Recommend:
    - yfinance (free, limited historical data)
    - Earnings calendar from Yahoo Finance / MarketWatch (free, limited prediction)
    - For production: Zacks or TradingView API (paid)
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "Catastrophe-Analyzer"})

    def fetch_recent_earnings(self, days_lookback: int = 7, min_surprise_pct: float = 5.0) -> List[EarningsSurprise]:
        """Fetch recent earnings surprises.

        Note: Requires paid API or web scraping. This is a placeholder.
        In production, use Zacks, Yahoo Finance Pro, or TradingView.

        Args:
            days_lookback: how far back to look
            min_surprise_pct: only return surprises >= this %

        Returns:
            List of EarningsSurprise objects
        """
        events = []

        # Placeholder: In production, integrate with paid earnings API
        # Example integration points:
        # - Zacks (zacks.com API)
        # - TradingView (https://tradingview.com/markets/earnings/)
        # - Yahoo Finance (yfinance + manual calendar scraping)
        # - Seeking Alpha (requires scraping)

        log.warning(
            "EarningsFeed.fetch_recent_earnings() requires paid API integration. "
            "Consider: Zacks, TradingView, or Yahoo Finance Pro."
        )

        return events

    def detect_guidance_changes(self, ticker: str) -> Optional[EarningsSurprise]:
        """Detect guidance cuts/raises (material for swing trades).

        Guidance changes often lead to 5-15% moves over 1-5 days.

        Args:
            ticker: stock ticker

        Returns:
            EarningsSurprise if guidance change detected, None otherwise
        """
        # Placeholder: would need real-time earnings/guidance data
        return None

    def cache_to_file(self, events: List[EarningsSurprise], path: str = "/app/data/earnings_events.jsonl"):
        """Cache earnings events to file.

        Args:
            events: list of EarningsSurprise objects
            path: file path to write to
        """
        try:
            with open(path, "a") as f:
                for event in events:
                    f.write(json.dumps(event.to_dict()) + "\n")
            log.info(f"Cached {len(events)} earnings events to {path}")
        except Exception as e:
            log.error(f"Error caching earnings events: {e}")

    def load_cache(self, path: str = "/app/data/earnings_events.jsonl", days_lookback: int = 7) -> List[EarningsSurprise]:
        """Load cached earnings surprises from recent period.

        Args:
            path: file path to read from
            days_lookback: only return events from last N days

        Returns:
            List of EarningsSurprise objects
        """
        events = []
        cutoff = (datetime.now() - timedelta(days=days_lookback)).isoformat()[:10]

        try:
            with open(path, "r") as f:
                for line in f:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("report_date", "") >= cutoff:
                        events.append(EarningsSurprise(**data))
        except FileNotFoundError:
            log.debug(f"No cache file at {path}")
        except Exception as e:
            log.error(f"Error loading earnings cache: {e}")

        return events


class EarningsCalendarIntegration:
    """Helper to integrate earnings calendar data.

    Recommendation: Use yfinance + manual scraping or paid API.
    """

    @staticmethod
    def get_upcoming_earnings(tickers: List[str], days_ahead: int = 7) -> dict:
        """Get upcoming earnings dates for tickers.

        Args:
            tickers: list of stock tickers
            days_ahead: how many days to look ahead

        Returns:
            dict mapping ticker -> earnings_date (YYYY-MM-DD)
        """
        # Placeholder: would use yfinance or earnings calendar API
        # yfinance has limited earnings data; consider:
        # - MarketWatch earnings calendar (requires scraping)
        # - Yahoo Finance (yfinance limited)
        # - TradingView API
        return {}

    @staticmethod
    def monitor_for_earnings_in_range(ticker: str, start_date: str, end_date: str) -> bool:
        """Check if ticker has earnings in a date range.

        Args:
            ticker: stock ticker
            start_date: YYYY-MM-DD
            end_date: YYYY-MM-DD

        Returns:
            True if earnings expected in range
        """
        # Placeholder
        return False
