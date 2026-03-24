import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database_manager import DatabaseManager  # noqa: E402


class YieldDashboardTests(unittest.TestCase):
    def test_dashboard_rows_exist_for_requested_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(data_dir=tmpdir)
            categories = ["cybersecurity", "clinical_regulatory_binary", "product_safety_recall"]
            dashboard = db.get_category_yield_dashboard(days=30, categories=categories)

            self.assertEqual(dashboard["window_days"], 30)
            rows = dashboard["rows"]
            self.assertEqual(len(rows), 3)

            by_cat = {row["event_category"]: row for row in rows}
            for category in categories:
                self.assertIn(category, by_cat)
                self.assertEqual(by_cat[category]["events"], 0)
                self.assertEqual(by_cat[category]["watches"], 0)
                self.assertEqual(by_cat[category]["analyses"], 0)
                self.assertEqual(by_cat[category]["signals"], 0)

    def test_dashboard_funnel_and_lookback_math(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(data_dir=tmpdir)
            today = datetime.now().strftime("%Y-%m-%d")
            old_day = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")

            # In-window cybersecurity record should count.
            db.add_event(
                {
                    "event_date": today,
                    "company": "Acme Cyber",
                    "ticker": "ACYB",
                    "event_category": "cybersecurity",
                    "event_subtype": "Material Cyber Disclosure",
                    "severity": "High",
                    "source": "unit-test",
                    "url": "https://example.com/cyber",
                    "summary": "Material cybersecurity incident disclosed in 8-k.",
                }
            )
            db.add_watch_if_new(
                {
                    "ticker": "ACYB",
                    "company": "Acme Cyber",
                    "event_date": today,
                    "event_category": "cybersecurity",
                    "status": "ACTIVE",
                }
            )
            db.add_analysis(
                {
                    "ticker": "ACYB",
                    "event_date": today,
                    "event_category": "cybersecurity",
                    "pre_event_price": 100,
                    "current_price": 88,
                    "min_price_post_event": 85,
                    "max_drop_pct": 15,
                    "current_rsi": 28,
                    "volume_spike_at_event": 2.1,
                }
            )
            db.add_signal(
                {
                    "ticker": "ACYB",
                    "event_date": today,
                    "event_category": "cybersecurity",
                    "signal_type": "BUY_OPPORTUNITY",
                    "confidence_level": "HIGH",
                    "confidence_score": 80,
                    "risk_reward_ratio": 2.0,
                }
            )

            # Out-of-window clinical record should be excluded for 30-day window.
            db.add_event(
                {
                    "event_date": old_day,
                    "company": "Old Biotech",
                    "ticker": "OBIO",
                    "event_category": "clinical_regulatory_binary",
                    "event_subtype": "FDA Complete Response Letter",
                    "severity": "High",
                    "source": "unit-test",
                    "url": "https://example.com/old",
                    "summary": "Old event outside lookback window.",
                }
            )

            dashboard = db.get_category_yield_dashboard(
                days=30,
                categories=["cybersecurity", "clinical_regulatory_binary"],
            )
            by_cat = {row["event_category"]: row for row in dashboard["rows"]}

            cyber = by_cat["cybersecurity"]
            self.assertEqual(cyber["events"], 1)
            self.assertEqual(cyber["watches"], 1)
            self.assertEqual(cyber["analyses"], 1)
            self.assertEqual(cyber["signals"], 1)
            self.assertEqual(cyber["event_to_watch_rate_pct"], 100.0)
            self.assertEqual(cyber["watch_to_analysis_rate_pct"], 100.0)
            self.assertEqual(cyber["analysis_to_signal_rate_pct"], 100.0)
            self.assertEqual(cyber["event_to_signal_rate_pct"], 100.0)

            clinical = by_cat["clinical_regulatory_binary"]
            self.assertEqual(clinical["events"], 0)
            self.assertEqual(clinical["watches"], 0)


if __name__ == "__main__":
    unittest.main()
