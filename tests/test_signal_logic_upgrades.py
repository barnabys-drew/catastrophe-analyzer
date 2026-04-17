"""
Tests for signal logic upgrades:
- ATR-based stop loss
- Earnings proximity guardrail
- Sector residual drop filter
- Short-sell candidate annotation for short_seller_report / going_concern / fraud
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from signal_generator import SignalGenerator  # noqa: E402


def _base_analysis(**overrides: Any) -> Dict[str, Any]:
    analysis = {
        "ticker": "ACME",
        "event_date": "2026-04-15",
        "event_category": "cybersecurity",
        "pre_event_price": 100.0,
        "event_anchor_price": 92.0,
        "current_price": 85.0,
        "min_price_post_event": 82.0,
        "min_price_post_breach": 82.0,
        "max_drop_pct": 18.0,
        "drop_48h_pct": 8.0,
        "recovery_days": None,
        "event_rsi": 25.0,
        "current_rsi": 25.0,
        "rsi_oversold": True,
        "price_below_ma20": True,
        "volume_spike_at_event": 3.0,
        "volume_spike_at_breach": 3.0,
        "avg_volume_20d": 1_000_000.0,
        "distress_score": 70,
        "impact_score": 72,
        "event_atr": 2.0,
        "atr": 2.0,
    }
    analysis.update(overrides)
    return analysis


def _generator(**signal_overrides: Any) -> SignalGenerator:
    settings = {
        "signals": {
            "rsi_oversold_threshold": 30,
            "price_drop_threshold": 10,
            "require_drop_within_48h": True,
            "drop_within_48h_threshold": 1.0,
            "recovery_days_threshold": 5,
            "volume_spike_threshold": 1.5,
            "min_price_for_signal": 2.5,
            "min_avg_volume_for_signal": 300_000,
            "min_confidence_for_signal": 0.5,
            "min_catalyst_score_for_signal": 30,
            "confidence_levels": {"high": 0.75, "medium": 0.50, "low": 0.25},
            "stop_loss_pct_floor_multiplier": 0.97,
            "atr_stop_multiplier": 1.5,
            "earnings_proximity_block_days": 3,
            "short_sell_continuation_multiplier": 0.5,
            "min_residual_drop_pct_vs_sector": None,
        }
    }
    signals_cfg = settings["signals"]
    assert isinstance(signals_cfg, dict)
    signals_cfg.update(signal_overrides)
    return SignalGenerator(settings=settings)


class SignalLogicUpgradeTests(unittest.TestCase):
    def test_atr_based_stop_tightens_stop_when_atr_is_small(self) -> None:
        gen = _generator()
        analysis = _base_analysis(event_atr=0.2, atr=0.2)  # 1.5*0.2 = 0.3 off $82 min
        stop = gen._calculate_stop_loss(analysis)
        # ATR stop = $81.70; pct stop = $79.54; tighter (higher) stop wins.
        self.assertAlmostEqual(stop, 81.70, places=2)

    def test_percent_floor_is_used_when_atr_wide(self) -> None:
        gen = _generator()
        analysis = _base_analysis(event_atr=5.0, atr=5.0)  # 1.5*5.0=7.5 off $82 min = $74.50
        stop = gen._calculate_stop_loss(analysis)
        # ATR stop = $74.50; pct stop = $79.54; pct floor wins.
        self.assertAlmostEqual(stop, 79.54, places=2)

    def test_atr_stop_falls_back_to_pct_floor_when_atr_missing(self) -> None:
        gen = _generator()
        analysis = _base_analysis(event_atr=0.0, atr=0.0)
        stop = gen._calculate_stop_loss(analysis)
        self.assertAlmostEqual(stop, 82.0 * 0.97, places=2)

    def test_earnings_proximity_blocks_non_earnings_category(self) -> None:
        gen = _generator()
        analysis = _base_analysis(days_to_next_earnings=1)
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertTrue(reason.startswith("earnings_proximity_block_failed"))

    def test_earnings_proximity_allows_earnings_category(self) -> None:
        gen = _generator()
        analysis = _base_analysis(
            days_to_next_earnings=1,
            event_category="negative_earnings_catalyst",
        )
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result, f"expected signal; got reason={reason}")

    def test_sector_residual_drop_filter_blocks_market_wide_move(self) -> None:
        gen = _generator(min_residual_drop_pct_vs_sector=5.0)
        analysis = _base_analysis(residual_drop_pct=2.0)  # below 5% residual
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertTrue(reason.startswith("sector_residual_drop_failed"))

    def test_sector_residual_drop_filter_allows_name_specific_move(self) -> None:
        gen = _generator(min_residual_drop_pct_vs_sector=5.0)
        analysis = _base_analysis(residual_drop_pct=12.0)
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result, f"expected signal; got reason={reason}")

    def test_short_sell_candidate_for_short_seller_report(self) -> None:
        gen = _generator()
        analysis = _base_analysis(event_category="short_seller_report")
        result, _ = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result)
        short = result.get("short_sell_candidate")
        self.assertIsNotNone(short)
        self.assertEqual(short["signal_type"], "SHORT_SELL_CANDIDATE")
        self.assertGreater(short["stop_loss"], short["entry_price"])
        self.assertLess(short["target_price"], short["entry_price"])

    def test_short_sell_candidate_not_attached_for_cyber(self) -> None:
        gen = _generator()
        analysis = _base_analysis(event_category="cybersecurity")
        result, _ = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result)
        self.assertNotIn("short_sell_candidate", result)


if __name__ == "__main__":
    unittest.main()
