import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from alert_manager import AlertManager  # noqa: E402


class AlertOrderingTests(unittest.TestCase):
    def test_orders_by_strength_then_lowest_price(self):
        signals = [
            {"ticker": "A", "confidence": 80, "price": 15.0},
            {"ticker": "B", "confidence": 95, "price": 50.0},
            {"ticker": "C", "confidence": 95, "price": 8.0},
            {"ticker": "D", "confidence_level": "HIGH", "suggested_entry": 7.5},
        ]
        ordered = AlertManager._order_signals_for_alerts(signals)
        ordered_tickers = [s["ticker"] for s in ordered]
        self.assertEqual(ordered_tickers[0], "C")
        self.assertEqual(ordered_tickers[1], "B")
        self.assertEqual(ordered_tickers[-1], "A")

    def test_dedupe_then_order_keeps_single_ticker(self):
        signals = [
            {"ticker": "XYZ", "confidence": 60, "price": 10.0},
            {"ticker": "XYZ", "confidence": 90, "price": 9.0, "event_subtype": "Ransomware"},
            {"ticker": "ABC", "confidence": 85, "price": 7.0},
        ]
        deduped = AlertManager._dedupe_one_company_per_ticker(signals)
        ordered = AlertManager._order_signals_for_alerts(deduped)
        tickers = [s["ticker"] for s in ordered]
        self.assertEqual(tickers.count("XYZ"), 1)
        self.assertEqual(tickers[0], "XYZ")


if __name__ == "__main__":
    unittest.main()
