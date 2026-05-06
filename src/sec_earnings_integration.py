"""Integration layer for SEC, earnings, and multi-source signals into main pipeline."""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

from sec_feed import SecFeed, SecEvent
from earnings_feed import EarningsFeed, EarningsSurprise
from multi_source_detector import MultiSourceDetector, MultiSourceSignal

log = logging.getLogger("sec_earnings_integration")


class SecEarningsIntegration:
    """Orchestrates SEC feeds, earnings data, and multi-source signal detection."""

    def __init__(self, config_path: str = "config/settings.json", lookback_days: int = 7):
        """Initialize integration.

        Args:
            config_path: path to settings.json
            lookback_days: how far back to fetch SEC/earnings data
        """
        self.config_path = config_path
        self.lookback_days = lookback_days

        # Initialize feeds
        self.sec_feed = SecFeed(lookback_days=lookback_days)
        self.earnings_feed = EarningsFeed()
        self.detector = MultiSourceDetector()

    def fetch_sec_signals(self, use_mock: bool = False) -> List[Dict]:
        """Fetch and parse SEC 8-K and Form 4 events into signal format.

        Args:
            use_mock: if True, use mock data instead of live SEC API

        Returns:
            List of signal dicts with ticker, category, description, confidence
        """
        signals = []

        try:
            # Fetch recent 8-Ks
            recent_8ks = self.sec_feed.fetch_recent_8ks(limit=50, use_mock=use_mock)
            for event in recent_8ks:
                signal = {
                    "ticker": event.ticker,
                    "event_category": "sec_8k",
                    "item_type": event.item_type,
                    "item_description": event.item_description,
                    "source": "sec",
                    "filed_date": event.filing_date,
                    "url": event.url,
                    "raw_event": event,
                }
                signals.append(signal)

            # Fetch Form 4 insider trades
            # Would normally fetch for specific tickers, but for now get from recent 8-K tickers
            tickers_to_check = set(e.ticker for e in recent_8ks)[:10]  # Limit to top 10
            for ticker in tickers_to_check:
                form4s = self.sec_feed.fetch_form4_insider_trades(ticker, use_mock=use_mock)
                for event in form4s:
                    signal = {
                        "ticker": event.ticker,
                        "event_category": "sec_form4",
                        "item_type": event.item_type,
                        "item_description": event.item_description,
                        "source": "sec",
                        "filed_date": event.filing_date,
                        "url": event.url,
                        "raw_event": event,
                    }
                    signals.append(signal)

        except Exception as e:
            log.error(f"Error fetching SEC signals: {e}")

        return signals

    def fetch_earnings_signals(self) -> List[Dict]:
        """Fetch earnings surprise events into signal format.

        Returns:
            List of signal dicts with ticker, surprise_pct, guidance change
        """
        signals = []

        try:
            recent_earnings = self.earnings_feed.fetch_recent_earnings(lookback_days=self.lookback_days)
            for event in recent_earnings:
                signal = {
                    "ticker": event.ticker,
                    "event_category": "earnings_surprise",
                    "eps_surprise_pct": event.eps_surprise_pct,
                    "revenue_surprise_pct": event.revenue_surprise_pct,
                    "guidance_change": event.guidance_change,
                    "analyst_rating_change": event.analyst_rating_change,
                    "source": "earnings",
                    "report_date": event.report_date,
                    "raw_event": event,
                }
                signals.append(signal)

        except Exception as e:
            log.error(f"Error fetching earnings signals: {e}")

        return signals

    def detect_multi_source_signals(
        self,
        sec_signals: Optional[List[Dict]] = None,
        earnings_signals: Optional[List[Dict]] = None,
        min_confidence: float = 70.0,
    ) -> List[MultiSourceSignal]:
        """Detect high-confidence signals from multi-source confirmation.

        Args:
            sec_signals: optional pre-fetched SEC signals (fetches if None)
            earnings_signals: optional pre-fetched earnings signals (fetches if None)
            min_confidence: minimum confidence threshold (0-100)

        Returns:
            List of MultiSourceSignal objects sorted by confidence
        """
        if sec_signals is None:
            sec_signals = self.fetch_sec_signals()
        if earnings_signals is None:
            earnings_signals = self.fetch_earnings_signals()

        # Convert raw signals to multi-source detector format
        sec_ms_signals = self.detector.detect_sec_signals()
        earnings_ms_signals = self.detector.detect_earnings_signals()

        # Combine and rank
        combined = self.detector.combine_signals(
            sec_signals=sec_ms_signals,
            earnings_signals=earnings_ms_signals,
        )

        # Filter by confidence
        filtered = self.detector.filter_by_threshold(combined, min_confidence=min_confidence)

        return filtered

    def cache_events_to_file(self, sec_signals: List[Dict], earnings_signals: List[Dict]) -> None:
        """Cache SEC and earnings events for later analysis.

        Args:
            sec_signals: list of SEC signal dicts
            earnings_signals: list of earnings signal dicts
        """
        try:
            # Cache SEC events
            if sec_signals:
                sec_events = [s.get("raw_event") for s in sec_signals if "raw_event" in s]
                if sec_events:
                    self.sec_feed.cache_to_file(sec_events, path="/app/data/sec_events.jsonl")

            # Cache earnings events
            if earnings_signals:
                earnings_events = [s.get("raw_event") for s in earnings_signals if "raw_event" in s]
                if earnings_events:
                    self.earnings_feed.cache_to_file(earnings_events, path="/app/data/earnings_events.jsonl")

        except Exception as e:
            log.error(f"Error caching events: {e}")

    def run_once(self, use_mock: bool = False) -> Dict:
        """Run one complete SEC+earnings integration cycle.

        Args:
            use_mock: if True, use mock data for testing

        Returns:
            Summary dict with signal counts and top signals
        """
        log.info("Starting SEC+earnings integration cycle...")

        # Fetch signals from all sources
        sec_signals = self.fetch_sec_signals(use_mock=use_mock)
        earnings_signals = self.fetch_earnings_signals()

        log.info(f"Fetched {len(sec_signals)} SEC signals")
        log.info(f"Fetched {len(earnings_signals)} earnings signals")

        # Cache for future reference
        self.cache_events_to_file(sec_signals, earnings_signals)

        # Detect multi-source confirmations
        multi_source_signals = self.detect_multi_source_signals(
            sec_signals=sec_signals,
            earnings_signals=earnings_signals,
            min_confidence=70.0,
        )

        log.info(f"Detected {len(multi_source_signals)} high-confidence multi-source signals")

        # Return summary
        return {
            "sec_signals_found": len(sec_signals),
            "earnings_signals_found": len(earnings_signals),
            "multi_source_high_confidence": len(multi_source_signals),
            "top_signals": multi_source_signals[:5],  # Top 5 by confidence
        }
