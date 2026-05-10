"""Tests for Task #43 partial-window signal logic.

The partial-window fix lets CA produce buy_signals same-day on catastrophe
events with <2 post-event trading bars, where the prior code aborted with
"Not enough post-event price data" and waited 3+ days.

Coverage in this module focuses on signal_generator._evaluate_buy_signal,
where the gate logic for partial windows lives. stock_analyzer's windowed-
metric reliability flag construction is covered by sub-piece 4's
historical-event validation (requires real price history).

Test matrix:
- Full-window backward-compat: existing behavior unchanged
- Partial-window with sufficient drop fires same-day
- Partial-window without drop rejects appropriately
- Reliability flags propagate to buy_signal output
- Edge cases: missing flags (back-compat), reliable=True override
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
    """Full-window analysis fixture. Catches buy_signal by default."""
    analysis = {
        "ticker": "ACME",
        "event_date": "2026-05-08",
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
        # Reliability flags default: full-window event, both metrics reliable
        "partial_window": False,
        "available_post_event_bars": 5,
        "drop_48h_reliable": True,
        "recovery_reliable": True,
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


class FullWindowBackwardCompat(unittest.TestCase):
    """Full-window analyses must behave exactly as before."""

    def test_full_window_with_drop_fires(self) -> None:
        gen = _generator()
        analysis = _base_analysis()
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result, f"full-window analysis should fire; got reason={reason}")
        self.assertEqual(result["signal_type"], "BUY_OPPORTUNITY")

    def test_full_window_below_drop48h_threshold_rejects(self) -> None:
        """Existing rejection reason must still fire when reliable + below threshold."""
        gen = _generator()
        analysis = _base_analysis(drop_48h_pct=0.5)  # below 1.0 threshold
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "drop_within_48h_threshold_failed")

    def test_missing_reliability_flags_default_to_full_window(self) -> None:
        """Back-compat: legacy analyses without reliability flags act as full-window."""
        gen = _generator()
        analysis = _base_analysis()
        # Strip the new fields to simulate a legacy upstream
        for f in ("partial_window", "available_post_event_bars", "drop_48h_reliable", "recovery_reliable"):
            analysis.pop(f, None)
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result, f"legacy analysis should fire; got reason={reason}")


class PartialWindowSignalGate(unittest.TestCase):
    """The new behavior: partial-window analyses can produce buy_signals same-day."""

    def _partial(self, **overrides: Any) -> Dict[str, Any]:
        defaults: Dict[str, Any] = {
            "partial_window": True,
            "available_post_event_bars": 1,
            "drop_48h_reliable": False,
            "drop_48h_pct": None,
            "recovery_reliable": False,
            "recovery_days": None,
        }
        defaults.update(overrides)  # caller's overrides win
        return _base_analysis(**defaults)

    def test_partial_window_with_sufficient_max_drop_fires(self) -> None:
        """The whole point: a partial-window event with a real intraday drop fires."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=18.0)  # well above 10% threshold
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result, f"partial-window with strong drop should fire; got {reason}")
        self.assertTrue(result["partial_window"])
        self.assertEqual(result["available_post_event_bars"], 1)

    def test_partial_window_below_drop_threshold_rejects_at_max_drop_gate(self) -> None:
        """With max_drop_pct under threshold, the existing significant_drop gate rejects."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=5.0)  # below 10%
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "price_drop_threshold_failed")

    def test_partial_window_skips_drop_48h_gate(self) -> None:
        """Even with drop_48h_pct=None and drop_48h_reliable=False, signal can fire."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=15.0, drop_48h_pct=None)
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(
            result, f"partial-window must not block on missing 48h metric; got {reason}"
        )

    def test_partial_window_with_zero_post_event_bars(self) -> None:
        """0 available bars: max_drop_pct=0 → fails at price_drop_threshold (correct)."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=0.0, available_post_event_bars=0)
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "price_drop_threshold_failed")

    def test_partial_window_buy_signal_carries_diagnostic_fields(self) -> None:
        """The buy_signal must surface partial_window + bar count for human review."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=20.0, available_post_event_bars=1)
        result, _ = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(result)
        self.assertIn("partial_window", result)
        self.assertIn("available_post_event_bars", result)
        self.assertTrue(result["partial_window"])
        self.assertEqual(result["available_post_event_bars"], 1)

    def test_partial_window_volume_spike_still_required(self) -> None:
        """Volume spike at event is reliable even with 1 post-event bar — must still gate."""
        gen = _generator()
        analysis = self._partial(max_drop_pct=15.0, volume_spike_at_event=1.0)  # below 1.5
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "volume_spike_threshold_failed")

    def test_partial_window_rsi_or_below_ma_still_required(self) -> None:
        """Technical-weakness gate (RSI or below-MA) still applies on partial windows."""
        gen = _generator()
        analysis = self._partial(
            max_drop_pct=15.0, event_rsi=50.0, current_rsi=50.0,
            rsi_oversold=False, price_below_ma20=False,
        )
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "technical_weakness_condition_failed")


class ReliabilityFlagOverrides(unittest.TestCase):
    """Reliability flags must override drop_48h_pct interpretation."""

    def test_reliable_true_with_low_48h_drop_still_blocks(self) -> None:
        """If drop_48h_reliable=True is asserted, the gate must fire normally."""
        gen = _generator()
        analysis = _base_analysis(
            drop_48h_reliable=True,  # explicit
            partial_window=False,
            drop_48h_pct=0.2,
        )
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNone(result)
        self.assertEqual(reason, "drop_within_48h_threshold_failed")

    def test_reliable_false_with_low_48h_drop_skips_gate(self) -> None:
        """Symmetrically, drop_48h_reliable=False must skip the 48h gate even
        when the field has a low value (because the value is unreliable)."""
        gen = _generator()
        analysis = _base_analysis(
            drop_48h_reliable=False,
            partial_window=True,
            available_post_event_bars=1,
            drop_48h_pct=0.2,  # below threshold but unreliable
        )
        result, reason = gen._evaluate_buy_signal(analysis)
        self.assertIsNotNone(
            result, f"unreliable drop_48h must not block; got reason={reason}"
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
