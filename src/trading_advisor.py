"""
Trading Advisor - Convert CA signals into actionable trade recommendations.
Maps event categories to historical trading patterns with conviction scoring.
"""

from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class TradeRecommendation:
    ticker: str
    direction: str  # LONG or SHORT
    conviction: int  # 0-100
    thesis: str
    entry_setup: str
    stop_loss: str
    profit_target: str
    risk_reward: str


class TradingAdvisor:
    """
    Maps catastrophe events to historical trading patterns.
    Returns 2-3 recommended trades per signal with full context.
    """

    # Event category → historical trades mapping
    EVENT_TRADE_PATTERNS = {
        "GEO_CRISIS": {
            "description": "Geopolitical events (war, coups, sanctions)",
            "trades": [
                {
                    "ticker": "DBC",  # Commodities ETF (oil/energy spike)
                    "direction": "LONG",
                    "base_conviction": 75,
                    "thesis": "Geopolitical tensions typically spike oil/energy prices",
                    "entry": "Within 24h of headline, on dip to support",
                    "stop": "Below recent swing low",
                    "target": "+8-15% in 1-4 weeks",
                    "risk_reward": "1:3"
                },
                {
                    "ticker": "GLD",  # Gold ETF
                    "direction": "LONG",
                    "base_conviction": 70,
                    "thesis": "Safe-haven bid during geopolitical stress",
                    "entry": "Break above 200-day MA or on dip",
                    "stop": "Below 50-day MA",
                    "target": "+5-10% in 2-6 weeks",
                    "risk_reward": "1:2"
                },
                {
                    "ticker": "IYM",  # Metals & Mining ETF
                    "direction": "SHORT",
                    "base_conviction": 60,
                    "thesis": "Mining operations disrupted; cyclical weakness",
                    "entry": "Breakdown below support or on bounce",
                    "stop": "Above recent swing high",
                    "target": "-5-12% in 2-4 weeks",
                    "risk_reward": "1:2"
                }
            ]
        },
        "SUPPLY_SHOCK": {
            "description": "Supply disruptions (shipping, ports, commodity limits)",
            "trades": [
                {
                    "ticker": "XME",  # Metals ETF (commodities usually spike)
                    "direction": "LONG",
                    "base_conviction": 72,
                    "thesis": "Supply limits drive commodity price appreciation",
                    "entry": "Within 48h on weakness, above support",
                    "stop": "Below prior support level",
                    "target": "+6-14% in 1-3 weeks",
                    "risk_reward": "1:2"
                },
                {
                    "ticker": "USO",  # Oil ETF
                    "direction": "LONG",
                    "base_conviction": 75,
                    "thesis": "Energy supply disruptions are bullish for crude",
                    "entry": "On dip to 20-day MA or support",
                    "stop": "Below recent swing low",
                    "target": "+8-18% in 1-4 weeks",
                    "risk_reward": "1:3"
                }
            ]
        },
        "FINANCIAL_CRISIS": {
            "description": "Bank failures, credit stress, systemic risk",
            "trades": [
                {
                    "ticker": "TLT",  # Treasury bonds (flight to safety)
                    "direction": "LONG",
                    "base_conviction": 80,
                    "thesis": "Crisis = flight to safety = bond rally",
                    "entry": "On initial panic, hold through bounces",
                    "stop": "Below recent swing low",
                    "target": "+4-8% in 2-4 weeks",
                    "risk_reward": "1:3"
                },
                {
                    "ticker": "FAZ",  # Financials 3x inverse (shorts banks)
                    "direction": "LONG",
                    "base_conviction": 70,
                    "thesis": "Banking crisis = financial sector weakness",
                    "entry": "Within 24h, hold for 2-3 weeks",
                    "stop": "Below entry + 5%",
                    "target": "+10-25% in 2-4 weeks",
                    "risk_reward": "1:2"
                }
            ]
        },
        "PANDEMIC": {
            "description": "Disease outbreaks, quarantines, health crisis",
            "trades": [
                {
                    "ticker": "XLV",  # Healthcare / Biotech
                    "direction": "LONG",
                    "base_conviction": 65,
                    "thesis": "Healthcare outperforms during health crises",
                    "entry": "On market panic, above 50-day MA",
                    "stop": "Below 20-day MA",
                    "target": "+5-12% in 1-4 weeks",
                    "risk_reward": "1:2"
                },
                {
                    "ticker": "ARKK",  # Innovation (biotech heavy)
                    "direction": "LONG",
                    "base_conviction": 60,
                    "thesis": "Vaccine/treatment narratives drive innovation",
                    "entry": "Within 72h on dip",
                    "stop": "Below recent swing low",
                    "target": "+8-15% in 2-6 weeks",
                    "risk_reward": "1:2"
                }
            ]
        },
        "POLITICAL_SHOCK": {
            "description": "Elections, coups, policy reversals, political crisis",
            "trades": [
                {
                    "ticker": "GLD",  # Gold (uncertainty hedge)
                    "direction": "LONG",
                    "base_conviction": 65,
                    "thesis": "Political uncertainty = safe-haven demand",
                    "entry": "On dip to support or 50-day MA",
                    "stop": "Below 20-day MA",
                    "target": "+4-10% in 1-4 weeks",
                    "risk_reward": "1:2"
                },
                {
                    "ticker": "VIX",  # Volatility index
                    "direction": "LONG",
                    "base_conviction": 75,
                    "thesis": "Political shock = volatility spike",
                    "entry": "Within 24h on reversal",
                    "stop": "Below entry - 3%",
                    "target": "+15-40% in 1-2 weeks",
                    "risk_reward": "1:3"
                }
            ]
        }
    }

    def get_recommendations(
        self,
        ca_signal: Dict,
        max_trades: int = 3
    ) -> List[TradeRecommendation]:
        """
        Convert a CA signal to trade recommendations.

        Args:
            ca_signal: {"ticker", "event_category", "event_subtype", "confidence", "issue_summary"}
            max_trades: Maximum number of trade recommendations to return

        Returns:
            List of TradeRecommendation objects ranked by conviction
        """
        event_category = ca_signal.get("event_category", "").upper()
        ca_confidence = ca_signal.get("confidence", 50)  # 0-100

        # If event category not in mapping, return empty
        if event_category not in self.EVENT_TRADE_PATTERNS:
            return []

        pattern = self.EVENT_TRADE_PATTERNS[event_category]
        trades_config = pattern.get("trades", [])

        recommendations = []
        for trade_cfg in trades_config:
            # Adjust conviction based on CA confidence level
            adjusted_conviction = int(trade_cfg["base_conviction"] * (ca_confidence / 100))
            adjusted_conviction = min(100, max(0, adjusted_conviction))

            rec = TradeRecommendation(
                ticker=trade_cfg["ticker"],
                direction=trade_cfg["direction"],
                conviction=adjusted_conviction,
                thesis=trade_cfg["thesis"],
                entry_setup=trade_cfg["entry"],
                stop_loss=trade_cfg["stop"],
                profit_target=trade_cfg["target"],
                risk_reward=trade_cfg["risk_reward"]
            )
            recommendations.append(rec)

        # Sort by conviction (highest first) and return top N
        recommendations.sort(key=lambda x: x.conviction, reverse=True)
        return recommendations[:max_trades]

    def format_discord_message(self, ca_signal: Dict, recommendations: List[TradeRecommendation]) -> str:
        """Format trade recommendations as a Discord embed-friendly message."""
        event_cat = ca_signal.get("event_category", "UNKNOWN")
        ticker = ca_signal.get("ticker", "UNKNOWN")
        summary = ca_signal.get("issue_summary", "")

        lines = [
            f"🔥 **Trading Advice: {event_cat}** | Trigger: {ticker}",
            f"Summary: {summary}",
            ""
        ]

        for i, rec in enumerate(recommendations, 1):
            conviction_bar = "█" * (rec.conviction // 10) + "░" * (10 - rec.conviction // 10)
            lines.append(
                f"**Trade {i}: {rec.direction} {rec.ticker}** [{conviction_bar}] {rec.conviction}%\n"
                f"Thesis: {rec.thesis}\n"
                f"Entry: {rec.entry_setup}\n"
                f"Stop: {rec.stop_loss}\n"
                f"Target: {rec.profit_target}\n"
                f"Risk/Reward: {rec.risk_reward}\n"
            )

        lines.append("⚠️ These are historical patterns, not financial advice.")
        return "\n".join(lines)
