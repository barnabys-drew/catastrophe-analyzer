"""
Tests for the post-signal outcome tracker.
"""

from __future__ import annotations

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List, Optional


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from outcome_tracker import (  # noqa: E402
    HORIZON_DAYS,
    compute_outcomes,
    summarize_outcomes,
    update_outcomes,
)


def _fixed_history(start_date: str, prices: List[float]) -> Dict[str, Any]:
    """Build a synthetic price history with sequential trading days."""
    from datetime import datetime, timedelta, timezone

    start = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    dates = []
    cursor = start
    while len(dates) < len(prices):
        # include weekend days for simplicity; outcome tracker doesn't enforce
        # weekday-only bars because the data source already filters.
        dates.append(cursor.strftime("%Y-%m-%d"))
        cursor = cursor + timedelta(days=1)
    return {"prices": list(prices), "dates": dates, "volumes": [0] * len(prices)}


class OutcomeTrackerTests(unittest.TestCase):
    def test_compute_outcomes_returns_and_hits(self) -> None:
        signal = {
            "ticker": "ACME",
            "signal_date": "2026-04-15T12:00:00",
            "event_date": "2026-04-15",
            "event_category": "cybersecurity",
            "confidence_level": "HIGH",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target_price": 110.0,
            "target_template": "partial_reversion",
        }
        # Day 0 -> 100, Day 1 -> 101, Day 5 -> 105, Day 10 -> 112 (target hit),
        # Day 20 -> 108.
        prices = [100, 101, 102, 103, 104, 105, 107, 108, 110, 111, 112] + [108] * 20
        history = _fixed_history("2026-04-16", prices)

        outcome = compute_outcomes(signal, history)
        self.assertTrue(outcome.hit_target)
        self.assertFalse(outcome.hit_stop)
        self.assertEqual(outcome.horizon_days_observed, 20)
        self.assertAlmostEqual(outcome.returns_pct[1], 0.0, places=2)  # (100 - 100)/100
        self.assertAlmostEqual(outcome.returns_pct[5], 4.0, places=2)  # 104 -> +4%
        # Day 10 = index 9 (zero-based) after start_idx=0 -> prices[9] = 111
        self.assertAlmostEqual(outcome.returns_pct[10], 11.0, places=2)

    def test_compute_outcomes_stop_hit(self) -> None:
        signal = {
            "ticker": "BETA",
            "signal_date": "2026-04-15T12:00:00",
            "entry_price": 100.0,
            "stop_loss": 95.0,
            "target_price": 110.0,
        }
        prices = [99, 97, 95, 94, 90] + [92] * 20
        history = _fixed_history("2026-04-16", prices)
        outcome = compute_outcomes(signal, history)
        self.assertTrue(outcome.hit_stop)
        self.assertFalse(outcome.hit_target)

    def test_update_outcomes_appends_rows_once(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outcomes_csv = os.path.join(tmpdir, "signal_outcomes.csv")
            signal = {
                "ticker": "ACME",
                "signal_date": "2026-04-15T12:00:00",
                "event_date": "2026-04-15",
                "event_category": "cybersecurity",
                "confidence_level": "HIGH",
                "entry_price": 100.0,
                "stop_loss": 95.0,
                "target_price": 110.0,
            }
            prices = [100, 102, 104, 106, 108] + [110] * 20
            history = _fixed_history("2026-04-16", prices)

            def price_fn(_ticker: str, _days: int) -> Optional[Dict[str, Any]]:
                return history

            created = update_outcomes([signal], price_fn, outcomes_csv)
            self.assertEqual(len(created), 1)

            # Second call should not duplicate.
            created_again = update_outcomes([signal], price_fn, outcomes_csv)
            self.assertEqual(created_again, [])

            with open(outcomes_csv, "r", encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["ticker"], "ACME")
            self.assertEqual(rows[0]["event_category"], "cybersecurity")

    def test_summarize_outcomes_by_category_and_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            outcomes_csv = os.path.join(tmpdir, "signal_outcomes.csv")

            def price_fn(ticker: str, _days: int) -> Optional[Dict[str, Any]]:
                # Winner for ACME, loser for BETA
                if ticker == "ACME":
                    return _fixed_history("2026-04-16", [100, 101, 103, 105, 107, 110] + [110] * 20)
                if ticker == "BETA":
                    return _fixed_history("2026-04-16", [100, 98, 96, 94, 92, 90] + [90] * 20)
                return None

            signals = [
                {
                    "ticker": "ACME",
                    "signal_date": "2026-04-15T00:00:00",
                    "event_category": "cybersecurity",
                    "confidence_level": "HIGH",
                    "entry_price": 100.0,
                    "stop_loss": 95.0,
                    "target_price": 110.0,
                },
                {
                    "ticker": "BETA",
                    "signal_date": "2026-04-15T00:00:00",
                    "event_category": "cybersecurity",
                    "confidence_level": "MEDIUM",
                    "entry_price": 100.0,
                    "stop_loss": 95.0,
                    "target_price": 110.0,
                },
            ]
            update_outcomes(signals, price_fn, outcomes_csv)

            summary = summarize_outcomes(outcomes_csv, horizon=5)
            self.assertEqual(summary["samples"], 2)
            cyber = summary["by_category"]["cybersecurity"]
            self.assertEqual(cyber["samples"], 2)
            self.assertEqual(cyber["wins"], 1)
            self.assertAlmostEqual(cyber["win_rate"], 0.5, places=4)

            self.assertEqual(summary["by_confidence"]["HIGH"]["wins"], 1)
            self.assertEqual(summary["by_confidence"]["MEDIUM"]["wins"], 0)


if __name__ == "__main__":
    unittest.main()
