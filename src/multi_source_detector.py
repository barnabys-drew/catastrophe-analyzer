"""Multi-source event detector combining news, SEC, earnings, and insider trades."""
import logging
from typing import List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass

from sec_feed import SecFeed, SecEvent
from earnings_feed import EarningsFeed, EarningsSurprise

log = logging.getLogger("multi_source_detector")


@dataclass
class MultiSourceSignal:
    """Trade signal from multiple data sources."""
    ticker: str
    company_name: str
    event_type: str  # "sec_filing", "earnings_surprise", "insider_activity", "news", "litigation"
    confidence_score: float  # 0-100
    sources: List[str]  # which data sources triggered (news, sec, earnings, etc.)
    description: str
    urgency: str  # "high", "medium", "low"
    recommend_action: str  # "buy_dip", "sell_strength", "investigate", "hold"
    timestamp: str

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "event_type": self.event_type,
            "confidence_score": self.confidence_score,
            "sources": self.sources,
            "description": self.description,
            "urgency": self.urgency,
            "recommend_action": self.recommend_action,
            "timestamp": self.timestamp,
        }


class MultiSourceDetector:
    """Detects trading signals from news, SEC filings, earnings, insider activity."""

    def __init__(self):
        self.sec_feed = SecFeed(lookback_days=7)
        self.earnings_feed = EarningsFeed()

        # Confidence thresholds (lower = more signals fired)
        self.min_confidence_high = 70  # was 85
        self.min_confidence_medium = 50  # was 65
        self.min_confidence_low = 35  # was 50

    def detect_sec_signals(self) -> List[MultiSourceSignal]:
        """Detect signals from SEC 8-K and Form 4 filings.

        8-K items indicating distress:
        - 1.01: Material agreement/change in control
        - 2.02: Material cost/restructuring
        - 2.06: Material asset disposition
        - 8.01: Bankruptcy/going concern
        - 9.01: Litigation/legal proceedings

        Form 4 signals:
        - Heavy insider selling (distress)
        - Insider buying at lows (opportunity)
        """
        signals = []

        try:
            # Get recent 8-Ks
            recent_8ks = self.sec_feed.fetch_recent_8ks(limit=50)

            for event in recent_8ks:
                # Classify event severity
                if any(x in event.item_description for x in ["bankruptcy", "going concern", "liquidation"]):
                    confidence = 90
                    urgency = "high"
                    action = "sell_strength"
                elif any(x in event.item_description for x in ["restructuring", "impairment", "litigation"]):
                    confidence = 75
                    urgency = "high"
                    action = "sell_strength"
                elif any(x in event.item_description for x in ["material agreement", "merger", "acquisition"]):
                    confidence = 60
                    urgency = "medium"
                    action = "investigate"
                else:
                    confidence = 45
                    urgency = "low"
                    action = "hold"

                # Skip low-confidence signals unless explicitly configured
                if confidence < self.min_confidence_low:
                    continue

                signal = MultiSourceSignal(
                    ticker=event.ticker,
                    company_name=event.company_name,
                    event_type="sec_8k_filing",
                    confidence_score=confidence,
                    sources=["sec_edgar"],
                    description=f"8-K filing: {event.item_description}",
                    urgency=urgency,
                    recommend_action=action,
                    timestamp=datetime.now().isoformat(),
                )
                signals.append(signal)

        except Exception as e:
            log.error(f"Error detecting SEC signals: {e}")

        return signals

    def detect_earnings_signals(self) -> List[MultiSourceSignal]:
        """Detect signals from earnings surprises and guidance changes.

        High-confidence signals:
        - EPS miss >10% + guidance cut (downside continuation play)
        - EPS beat >10% + guidance raised (upside follow-through play)
        - Analyst downgrades on earnings miss
        """
        signals = []

        try:
            recent_earnings = self.earnings_feed.load_cache()

            for event in recent_earnings:
                # Check EPS surprise
                eps_surprise = abs(event.eps_surprise_pct)
                revenue_surprise = abs(event.revenue_surprise_pct)

                if eps_surprise < 5:
                    continue  # Minor surprise, skip

                # Determine signal
                if event.eps_surprise_pct < -10 and event.guidance_change == "lowered":
                    # Big miss + guidance cut = strong sell signal
                    confidence = 85
                    urgency = "high"
                    action = "sell_strength"
                    event_type = "earnings_miss_guidance_cut"
                elif event.eps_surprise_pct > 10 and event.guidance_change == "raised":
                    # Big beat + guidance raise = strong buy signal
                    confidence = 80
                    urgency = "high"
                    action = "buy_dip"
                    event_type = "earnings_beat_guidance_raise"
                elif event.eps_surprise_pct < -5:
                    # Earnings miss = sell
                    confidence = 60
                    urgency = "medium"
                    action = "sell_strength"
                    event_type = "earnings_miss"
                else:
                    # Smaller moves
                    confidence = 50
                    urgency = "medium"
                    action = "investigate"
                    event_type = "earnings_surprise"

                if confidence < self.min_confidence_low:
                    continue

                signal = MultiSourceSignal(
                    ticker=event.ticker,
                    company_name=event.company_name,
                    event_type=event_type,
                    confidence_score=confidence,
                    sources=["earnings"],
                    description=f"Earnings: EPS {event.eps_actual} vs {event.eps_estimate} (est), {event.eps_surprise_pct:+.1f}%",
                    urgency=urgency,
                    recommend_action=action,
                    timestamp=datetime.now().isoformat(),
                )
                signals.append(signal)

        except Exception as e:
            log.error(f"Error detecting earnings signals: {e}")

        return signals

    def combine_signals(self, news_signals: List = None, sec_signals: List = None, earnings_signals: List = None) -> List[MultiSourceSignal]:
        """Combine signals from multiple sources.

        When same ticker appears in multiple sources, boost confidence.
        Example: "SEC 8-K bankruptcy filing + news report of financial distress" = higher confidence.

        Args:
            news_signals: signals from news scraper (optional)
            sec_signals: signals from SEC filings
            earnings_signals: signals from earnings surprises

        Returns:
            Combined and ranked signals
        """
        all_signals = []
        signal_by_ticker = {}

        for signal_list in [news_signals or [], sec_signals or [], earnings_signals or []]:
            for signal in signal_list:
                if signal.ticker not in signal_by_ticker:
                    signal_by_ticker[signal.ticker] = []
                signal_by_ticker[signal.ticker].append(signal)

        # Combine multi-source signals
        for ticker, signals in signal_by_ticker.items():
            if len(signals) > 1:
                # Multiple sources for same ticker = higher confidence
                confidence_boost = min(10 * (len(signals) - 1), 20)  # +10-20% confidence
                sources = list(set([s for sig in signals for s in sig.sources]))

                # Use highest confidence signal as base
                primary = max(signals, key=lambda x: x.confidence_score)
                combined_confidence = min(primary.confidence_score + confidence_boost, 100)

                combined = MultiSourceSignal(
                    ticker=ticker,
                    company_name=primary.company_name,
                    event_type=primary.event_type,
                    confidence_score=combined_confidence,
                    sources=sources,
                    description=primary.description + f" (corroborated by {len(signals)-1} other sources)",
                    urgency=primary.urgency,
                    recommend_action=primary.recommend_action,
                    timestamp=datetime.now().isoformat(),
                )
                all_signals.append(combined)
            else:
                all_signals.append(signals[0])

        # Sort by confidence
        all_signals.sort(key=lambda x: x.confidence_score, reverse=True)
        return all_signals

    def filter_by_threshold(self, signals: List[MultiSourceSignal], min_confidence: Optional[float] = None) -> List[MultiSourceSignal]:
        """Filter signals by confidence threshold.

        Args:
            signals: all detected signals
            min_confidence: override self.min_confidence_high

        Returns:
            Filtered signals
        """
        threshold = min_confidence or self.min_confidence_high
        return [s for s in signals if s.confidence_score >= threshold]
