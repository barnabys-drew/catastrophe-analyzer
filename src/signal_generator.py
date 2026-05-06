"""
Signal Generator Module
Generates buy/sell signals based on breach analysis
"""

import os
from typing import Any, List, Dict, Tuple, Optional
from datetime import datetime
import json
from config_loader import load_settings


def _safe_int_score(value: object) -> float:
    try:
        return max(0.0, min(100.0, float(str(value).strip() or "0")))
    except (TypeError, ValueError):
        return 0.0


def compute_signal_rank_score(signal: Dict) -> float:
    """Canonical ranking score: confidence (55%) + risk/reward (cap) + catalyst quality (15%)."""
    try:
        confidence = float(signal.get('confidence', 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence <= 0:
        level = str(signal.get("confidence_level", "")).upper().strip()
        confidence = {"HIGH": 90.0, "MEDIUM": 60.0, "LOW": 30.0}.get(level, 0.0)

    try:
        risk_reward = float(signal.get('risk_reward', {}).get('risk_reward_ratio', 0) or 0)
    except (TypeError, ValueError):
        risk_reward = 0.0

    impact = _safe_int_score(
        signal.get("triage_impact_score_used", signal.get("impact_score", 0))
    )
    distress = _safe_int_score(
        signal.get("triage_distress_score_used", signal.get("distress_score", 0))
    )
    catalyst_bonus = min((impact + distress) / 2.0, 100.0) * 0.15

    return (confidence * 0.55) + (min(risk_reward, 5.0) * 10.0) + catalyst_bonus


class SignalGenerator:
    """
    Generates trading signals based on breach events and stock analysis
    """

    def __init__(self, config_path: str = "../config/settings.json", settings: Dict | None = None):
        """
        Initialize signal generator with configuration

        Args:
            config_path: Path to settings.json
        """
        self.config = settings if settings is not None else load_settings(self._resolve_config_path(config_path))

        self.signal_config = self.config.get('signals', {})

    def _signal_thresholds_for_category(self, event_category: str) -> Dict:
        """
        Resolve signal thresholds for an event category with global fallback.
        """
        base = {
            'rsi_oversold_threshold': self.signal_config.get('rsi_oversold_threshold', 30),
            'price_drop_threshold': self.signal_config.get('price_drop_threshold', 10),
            'require_drop_within_48h': self.signal_config.get('require_drop_within_48h', True),
            'drop_within_48h_threshold': self.signal_config.get('drop_within_48h_threshold', 1.0),
            'recovery_days_threshold': self.signal_config.get('recovery_days_threshold', 5),
            'volume_spike_threshold': self.signal_config.get('volume_spike_threshold', 1.5),
            'min_price_for_signal': self.signal_config.get('min_price_for_signal', 2.5),
            'min_avg_volume_for_signal': self.signal_config.get('min_avg_volume_for_signal', 300000),
        }
        by_category = self.signal_config.get("by_category", {})
        if isinstance(by_category, dict):
            per_cat = by_category.get(event_category, {})
            if isinstance(per_cat, dict):
                for k in list(base.keys()):
                    if k in per_cat:
                        base[k] = per_cat[k]
        return base

    @staticmethod
    def _analysis_key(analysis: Dict) -> Tuple[str, str, str]:
        return (
            str(analysis.get("ticker", "")).strip(),
            str(analysis.get("event_date", analysis.get("breach_date", ""))).strip(),
            str(analysis.get("event_category", "")).strip(),
        )

    def _confidence_thresholds(self) -> Tuple[float, float]:
        """
        Return (high, medium) confidence cutoffs on a 0-100 scale.
        Supports config values in either 0-1 or 0-100 form.
        """
        levels = self.signal_config.get("confidence_levels", {}) or {}

        def _to_pct(value, default_pct: float) -> float:
            try:
                v = float(value)
            except (TypeError, ValueError):
                return default_pct
            if 0 <= v <= 1:
                return v * 100.0
            if 1 < v <= 100:
                return v
            return default_pct

        high = _to_pct(levels.get("high"), 70.0)
        medium = _to_pct(levels.get("medium"), 40.0)
        if medium > high:
            medium = high
        return high, medium

    @staticmethod
    def _category_target_template(event_category: str) -> str:
        """
        Return target template family by event category.
        - full_reversion: expect retrace toward pre-event level
        - partial_reversion: avoid assuming full fundamental recovery
        - momentum_extension: allow a modest upside extension for positive catalysts
        """
        category = (event_category or "").strip().lower()
        if category in {
            "financial_distress",
            "fraud_accounting_enforcement",
            "clinical_regulatory_binary",
            "product_safety_recall",
            "leadership_scandal",
            "dilutive_financing",
            "geopolitical_sanctions_exposure",
            "negative_earnings_catalyst",
            "short_seller_report",
            "credit_rating_action",
            "going_concern_auditor_change",
            "guidance_cut_preannouncement",
            "securities_class_action",
            "labor_action",
        }:
            return "partial_reversion"
        if category in {
            "positive_earnings_catalyst",
            "ma_corporate_action",
            "activist_13d_filing",
        }:
            return "momentum_extension"
        return "full_reversion"

    @staticmethod
    def _short_sell_categories() -> set:
        """
        Categories where the dominant signal is downside continuation rather than reversion.
        Buy-side rules still evaluate normally; these categories also produce a short-sell candidate
        when technical conditions confirm further weakness.
        """
        return {
            "short_seller_report",
            "going_concern_auditor_change",
            "fraud_accounting_enforcement",
        }

    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'signals': {
                'rsi_oversold_threshold': 30,
                'price_drop_threshold': 10,
                'require_drop_within_48h': True,
                'drop_within_48h_threshold': 1.0,
                'recovery_days_threshold': 5,
                'volume_spike_threshold': 1.5,
                'confidence_levels': {
                    'high': 0.75,
                    'medium': 0.5,
                    'low': 0.25
                }
            }
        }

    @staticmethod
    def _resolve_config_path(config_path: str) -> str:
        """Resolve relative config path from this module location."""
        if os.path.isabs(config_path):
            return config_path
        base_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.abspath(os.path.join(base_dir, config_path))

    def _evaluate_buy_signal(self, analysis: Dict) -> Tuple[Optional[Dict], str]:
        if 'error' in analysis:
            return None, "analysis_error"

        ticker = analysis.get('ticker')
        event_category = analysis.get('event_category', '') or ''
        thresholds = self._signal_thresholds_for_category(event_category)
        rsi_threshold = float(thresholds.get('rsi_oversold_threshold', 30))
        drop_threshold = float(thresholds.get('price_drop_threshold', 10))
        volume_threshold = float(thresholds.get('volume_spike_threshold', 1.5))
        require_drop_48h = bool(thresholds.get('require_drop_within_48h', True))
        drop_48h_threshold = float(thresholds.get('drop_within_48h_threshold', 1.0))
        min_price = float(thresholds.get("min_price_for_signal", 2.5))
        min_avg_volume = float(thresholds.get("min_avg_volume_for_signal", 300000))

        current_price = self._to_float(analysis.get("current_price"), 0.0)
        avg_volume_raw = analysis.get("avg_volume_20d")
        if current_price < min_price:
            return None, f"liquidity_price_floor_failed:{current_price:.2f}<{min_price:.2f}"
        if avg_volume_raw not in (None, ""):
            avg_volume_20d = self._to_float(avg_volume_raw, 0.0)
        else:
            avg_volume_20d = None
        if avg_volume_20d is not None and avg_volume_20d < min_avg_volume:
            return None, (
                f"liquidity_volume_floor_failed:{avg_volume_20d:.0f}<{min_avg_volume:.0f}"
            )

        rsi_value = analysis.get("event_rsi", analysis.get("current_rsi", 50))
        if isinstance(rsi_value, (int, float)):
            rsi_oversold = float(rsi_value) < rsi_threshold
        else:
            rsi_oversold = bool(analysis.get('rsi_oversold'))
        significant_drop = self._to_float(analysis.get('max_drop_pct', 0), 0.0) >= drop_threshold
        drop_48h_pct = self._to_float(
            analysis.get('drop_48h_pct', analysis.get('max_drop_pct', 0.0)),
            0.0,
        )
        dropped_within_48h = drop_48h_pct >= drop_48h_threshold
        below_ma = bool(analysis.get('price_below_ma20'))

        volume_spike_at_event = self._to_float(
            analysis.get('volume_spike_at_event', analysis.get('volume_spike_at_breach', 0)),
            0.0,
        )
        volume_spike = volume_spike_at_event > volume_threshold

        recovery_days_threshold = int(thresholds.get('recovery_days_threshold', 5))
        recovery_days = analysis.get('recovery_days')
        not_recovered_too_quickly = recovery_days is None or recovery_days >= recovery_days_threshold

        if not significant_drop:
            return None, "price_drop_threshold_failed"
        if require_drop_48h and not dropped_within_48h:
            return None, "drop_within_48h_threshold_failed"
        if not volume_spike:
            return None, "volume_spike_threshold_failed"
        if not (rsi_oversold or below_ma):
            return None, "technical_weakness_condition_failed"
        if not not_recovered_too_quickly:
            return None, "fast_recovery_filter_failed"

        min_catalyst = float(self.signal_config.get('min_catalyst_score_for_signal', 30))
        ds = self._safe_score(analysis.get('distress_score', 0))
        imp = self._safe_score(analysis.get('impact_score', 0))
        catalyst_avg = (ds + imp) / 2.0
        has_explicit_catalyst = ("distress_score" in analysis) or ("impact_score" in analysis)
        if has_explicit_catalyst and catalyst_avg < min_catalyst:
            return None, "min_catalyst_score_failed"

        # Earnings-proximity guardrail: do not open non-earnings long positions
        # that will straddle the next earnings print.
        earnings_days_block = int(
            self.signal_config.get('earnings_proximity_block_days', 3)
        )
        days_to_earnings = analysis.get('days_to_next_earnings')
        category_lower = str(event_category or '').strip().lower()
        earnings_categories = {
            "positive_earnings_catalyst",
            "negative_earnings_catalyst",
            "guidance_cut_preannouncement",
        }
        if (
            earnings_days_block > 0
            and isinstance(days_to_earnings, (int, float))
            and 0 <= days_to_earnings < earnings_days_block
            and category_lower not in earnings_categories
        ):
            return None, (
                f"earnings_proximity_block_failed:days_to_earnings={int(days_to_earnings)}"
            )

        # Sector-residual drop filter: reject candidates whose drop is mostly a
        # market-wide move rather than name-specific repricing. `sector_drop_pct`
        # and `residual_drop_pct` are supplied upstream when available; if the
        # fields are missing, the filter is skipped.
        residual_cfg = self.signal_config.get('min_residual_drop_pct_vs_sector')
        residual_drop = analysis.get('residual_drop_pct')
        if residual_cfg is not None and isinstance(residual_drop, (int, float)):
            try:
                min_residual = float(residual_cfg)
            except (TypeError, ValueError):
                min_residual = 0.0
            if float(residual_drop) < min_residual:
                return None, (
                    f"sector_residual_drop_failed:{residual_drop:.2f}<{min_residual:.2f}"
                )

        confidence_score = self._calculate_confidence(
            analysis,
            rsi_threshold=rsi_threshold,
            rsi_oversold=rsi_oversold,
            distress_score=self._safe_score(analysis.get("distress_score", 0)),
            impact_score=self._safe_score(analysis.get("impact_score", 0)),
        )

        signal = {
            'ticker': ticker,
            'signal_type': 'BUY_OPPORTUNITY',
            'signal_date': datetime.now().isoformat(),
            'event_date': analysis.get('event_date', analysis.get('breach_date')),
            'breach_date': analysis.get('event_date', analysis.get('breach_date')),
            'event_category': analysis.get('event_category', ''),
            'price': analysis.get('current_price'),
            'pre_event_price': analysis.get('pre_event_price', analysis.get('pre_breach_price')),
            'pre_breach_price': analysis.get('pre_event_price', analysis.get('pre_breach_price')),
            'rsi': analysis.get('event_rsi', analysis.get('current_rsi')),
            'max_drop_pct': analysis.get('max_drop_pct'),
            'drop_48h_pct': drop_48h_pct,
            'recovery_days': analysis.get('recovery_days'),
            'volume_spike_at_event': volume_spike_at_event,
            'volume_spike': volume_spike_at_event,
            'distress_score': self._safe_score(analysis.get('distress_score', 0)),
            'impact_score': self._safe_score(analysis.get('impact_score', 0)),
            'confidence': confidence_score,
            'confidence_level': self._get_confidence_level(confidence_score),
            'reasons': self._generate_reasons(analysis),
            'suggested_entry': self._calculate_entry_price(analysis),
            'suggested_stop_loss': self._calculate_stop_loss(analysis),
            'risk_reward': self._calculate_risk_reward(analysis),
            'atr': analysis.get('event_atr', analysis.get('atr', 0.0)),
            'days_to_next_earnings': analysis.get('days_to_next_earnings'),
            'residual_drop_pct': analysis.get('residual_drop_pct'),
            'float_shares': analysis.get('float_shares'),
            'short_interest_pct': analysis.get('short_interest_pct'),
        }
        short_sell = self._maybe_short_sell_signal(analysis, event_category)
        if short_sell is not None:
            signal['short_sell_candidate'] = short_sell
        return signal, "rule_passed"

    def _maybe_short_sell_signal(
        self,
        analysis: Dict,
        event_category: str,
    ) -> Optional[Dict]:
        """
        For categories where downside continuation dominates, attach a parallel
        short-sell candidate (entry / stop / target) derived from the existing
        analysis fields. This is advisory output; buy-side rules still evaluate
        normally. Returns None when the category is not eligible.
        """
        if str(event_category or '').strip().lower() not in self._short_sell_categories():
            return None

        current_price = self._to_float(analysis.get('current_price'), 0.0)
        pre_event_price = self._to_float(
            analysis.get('pre_event_price', analysis.get('pre_breach_price')),
            current_price,
        )
        min_price = self._to_float(
            analysis.get('min_price_post_event', analysis.get('min_price_post_breach', current_price)),
            current_price,
        )
        atr = self._to_float(
            analysis.get('event_atr', analysis.get('atr', 0.0)),
            0.0,
        )
        if current_price <= 0:
            return None

        atr_stop_multiplier = float(self.signal_config.get('atr_stop_multiplier', 1.5))
        # Short entry: current price; stop above the pre-event price plus an ATR
        # buffer so the stop isn't triggered by short-cover noise. Target: a
        # continuation leg sized to a multiple of the post-event drawdown.
        entry = current_price
        stop = max(pre_event_price, current_price) + max(atr * atr_stop_multiplier, current_price * 0.02)
        continuation_mult = float(self.signal_config.get('short_sell_continuation_multiplier', 0.5))
        target = max(0.0, min_price - (pre_event_price - min_price) * continuation_mult)
        risk = stop - entry
        reward = entry - target
        ratio = reward / risk if risk > 0 else 0.0
        return {
            'signal_type': 'SHORT_SELL_CANDIDATE',
            'entry_price': entry,
            'stop_loss': stop,
            'target_price': target,
            'risk_pct': (risk / entry * 100.0) if entry > 0 else 0.0,
            'reward_pct': (reward / entry * 100.0) if entry > 0 else 0.0,
            'risk_reward_ratio': ratio,
        }

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def generate_buy_signal(self, analysis: Dict) -> Optional[Dict]:
        signal, _ = self._evaluate_buy_signal(analysis)
        return signal

    @staticmethod
    def _safe_score(value: object, default: int = 0) -> int:
        try:
            return max(0, min(100, int(float(str(value).strip() or "0"))))
        except (TypeError, ValueError):
            return default

    def _calculate_confidence(
        self,
        analysis: Dict,
        *,
        rsi_threshold: float,
        rsi_oversold: bool,
        distress_score: int = 0,
        impact_score: int = 0,
    ) -> float:
        """
        Calculate confidence score 0-100.

        70 pts max from technical factors (RSI, drop, volume, MA, recovery).
        30 pts max from catalyst quality (distress + impact scores from triage).
        """
        raw_technical = 0

        if rsi_oversold:
            raw_technical += 25
        else:
            rsi_value = analysis.get("event_rsi", analysis.get("current_rsi"))
            if isinstance(rsi_value, (int, float)) and float(rsi_value) <= (rsi_threshold + 3):
                raw_technical += 10

        drop_pct = analysis.get('max_drop_pct', 0)
        if drop_pct > 10:
            raw_technical += 20
        elif drop_pct > 5:
            raw_technical += 10

        volume_spike = analysis.get('volume_spike_at_event', analysis.get('volume_spike_at_breach', 1.0))
        if volume_spike > 2.0:
            raw_technical += 20
        elif volume_spike > 1.5:
            raw_technical += 10

        if analysis.get('price_below_ma20'):
            raw_technical += 15

        recovery = analysis.get('recovery_days')
        if recovery is None:
            raw_technical += 20
        elif recovery < 3:
            raw_technical += 10

        technical_score = int(min(raw_technical, 100) * 0.70)

        ds = self._safe_score(distress_score or analysis.get("distress_score", 0))
        imp = self._safe_score(impact_score or analysis.get("impact_score", 0))
        catalyst_score = int(ds / 100.0 * 15) + int(imp / 100.0 * 15)

        # Multi-source confirmation bonus: add points when same ticker in 2+ sources
        multi_source_bonus = 0.0
        if analysis.get("multi_source_confirmed"):
            multi_source_bonus = float(
                self.signal_config.get("multi_source_confidence_bonus", 10.0)
            )

        return min(technical_score + catalyst_score + multi_source_bonus, 100)

    def _get_confidence_level(self, score: float) -> str:
        """
        Convert confidence score to level

        Args:
            score: Confidence score 0-100

        Returns:
            str: Confidence level (HIGH, MEDIUM, LOW)
        """
        high_cutoff, medium_cutoff = self._confidence_thresholds()
        if score >= high_cutoff:
            return 'HIGH'
        elif score >= medium_cutoff:
            return 'MEDIUM'
        else:
            return 'LOW'

    def _generate_reasons(self, analysis: Dict) -> List[str]:
        """
        Generate human-readable reasons for the signal

        Args:
            analysis: Stock analysis result

        Returns:
            list: Reasons for the signal
        """
        reasons = []

        ds = self._safe_score(analysis.get("distress_score", 0))
        imp = self._safe_score(analysis.get("impact_score", 0))
        if ds > 0 or imp > 0:
            reasons.append(f"Catalyst quality: distress {ds}/100, impact {imp}/100")

        rsi_for_signal = analysis.get("event_rsi", analysis.get("current_rsi"))
        if analysis.get('rsi_oversold') and isinstance(rsi_for_signal, (int, float)):
            reasons.append(f"Event-window RSI is {rsi_for_signal:.1f} (oversold)")

        drop_pct = analysis.get('max_drop_pct', 0)
        if drop_pct > 10:
            reasons.append(f"Stock dropped {drop_pct:.1f}% post-event")
        drop_48h_pct = analysis.get("drop_48h_pct")
        if isinstance(drop_48h_pct, (int, float)) and drop_48h_pct > 0:
            reasons.append(f"Stock dropped {drop_48h_pct:.1f}% within first 48h after event")

        volume_spike = analysis.get('volume_spike_at_event', analysis.get('volume_spike_at_breach', 1.0))
        reasons.append(f"Volume spike of {volume_spike:.1f}x at event confirms selling pressure")

        if analysis.get('price_below_ma20'):
            reasons.append("Price is below 20-day moving average")

        recovery = analysis.get('recovery_days')
        if recovery is None:
            reasons.append("Stock has not yet recovered to pre-event price")
        elif recovery < 5:
            reasons.append(f"Stock recovered in {recovery} days - quick recovery pattern")

        return reasons

    def _calculate_entry_price(self, analysis: Dict) -> float:
        """
        Suggest entry price (current price or limit order)

        Args:
            analysis: Stock analysis result

        Returns:
            float: Suggested entry price
        """
        current_price = analysis.get('current_price', 0)
        min_price = analysis.get('min_price_post_event', analysis.get('min_price_post_breach', current_price))

        # Suggest entry at current or slightly below min
        # If current price is near min, use current price
        # If current has rebounded, suggest limit order at min
        if current_price <= min_price * 1.05:  # Within 5% of minimum
            return current_price
        else:
            # Suggest limit order 2% above minimum
            return min_price * 1.02

    def _calculate_stop_loss(self, analysis: Dict) -> float:
        """
        Suggest stop loss price.

        Two placements are computed and the tighter of the two is taken so the
        stop is never wider than the percent floor even when ATR is noisy:
        - percent floor: `min_price * stop_loss_pct_floor_multiplier` (default 0.97)
        - ATR floor: `min_price - atr_stop_multiplier * event_atr` (default 1.5x)

        The stop never drops below zero.
        """
        min_price = float(
            analysis.get('min_price_post_event', analysis.get('min_price_post_breach', 0)) or 0.0
        )
        if min_price <= 0:
            return 0.0

        pct_mult = float(self.signal_config.get('stop_loss_pct_floor_multiplier', 0.97))
        pct_stop = min_price * pct_mult

        atr_mult = float(self.signal_config.get('atr_stop_multiplier', 1.5))
        atr = float(analysis.get('event_atr', analysis.get('atr', 0.0)) or 0.0)
        atr_stop = min_price - atr_mult * atr if atr > 0 else pct_stop

        # Take the tighter (higher) of the two to bound downside without letting
        # a very noisy ATR pull the stop well under the recent low.
        stop = max(pct_stop, atr_stop)
        return max(0.0, float(stop))

    def _calculate_risk_reward(self, analysis: Dict) -> Dict:
        """
        Calculate potential risk/reward

        Args:
            analysis: Stock analysis result

        Returns:
            dict: Risk/reward analysis
        """
        current_price = analysis.get('current_price', 0)
        entry_price = self._calculate_entry_price(analysis)
        stop_loss = self._calculate_stop_loss(analysis)
        pre_event_price = analysis.get(
            'pre_event_price',
            analysis.get('pre_breach_price', current_price * 1.05),
        )
        event_category = analysis.get('event_category', '')

        # Risk: from entry to stop loss
        risk = entry_price - stop_loss
        risk_pct = (risk / entry_price * 100) if entry_price > 0 else 0

        # Reward target is category-aware instead of one-size-fits-all full reversion.
        template = self._category_target_template(event_category)
        if template == "partial_reversion":
            target_price = entry_price + (pre_event_price - entry_price) * 0.6
        elif template == "momentum_extension":
            target_price = max(pre_event_price, entry_price * 1.06)
        else:
            target_price = pre_event_price

        # Reward: from entry to category template target
        reward = target_price - entry_price
        reward_pct = (reward / entry_price * 100) if entry_price > 0 else 0

        # Risk/reward ratio
        ratio = reward / risk if risk > 0 else 0

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target_price': target_price,
            'target_template': template,
            'risk_pct': risk_pct,
            'reward_pct': reward_pct,
            'risk_reward_ratio': ratio
        }

    def generate_signals_batch(self, analyses: List[Dict]) -> List[Dict]:
        """
        Generate signals from multiple analyses

        Args:
            analyses: List of analysis results

        Returns:
            list: Generated signals (only successful ones)
        """
        signals = []

        for analysis in analyses:
            signal = self.generate_buy_signal(analysis)
            if signal:
                signals.append(signal)

        return signals

    def generate_signals_with_diagnostics(
        self,
        analyses: List[Dict],
    ) -> Tuple[List[Dict], Dict[Tuple[str, str, str], Dict[str, Any]]]:
        """
        Generate candidate signals and include per-analysis gate diagnostics.
        """
        signals: List[Dict] = []
        diagnostics: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
        for analysis in analyses:
            key = self._analysis_key(analysis)
            signal, reason = self._evaluate_buy_signal(analysis)
            if signal is not None:
                diagnostics[key] = {
                    "decision": "RULE_PASSED",
                    "reason": reason,
                    "confidence": signal.get("confidence", ""),
                }
                signals.append(signal)
            else:
                diagnostics[key] = {
                    "decision": "RULE_REJECTED",
                    "reason": reason,
                }
        return signals, diagnostics

    def rank_signals(self, signals: List[Dict]) -> List[Dict]:
        """
        Rank signals by attractiveness

        Args:
            signals: List of generated signals

        Returns:
            list: Signals sorted by quality (best first)
        """
        return sorted(signals, key=compute_signal_rank_score, reverse=True)

    def filter_signals(self, signals: List[Dict], min_confidence: float = 0.5) -> List[Dict]:
        """
        Filter signals by confidence threshold

        Args:
            signals: List of signals
            min_confidence: Minimum confidence (0-1)

        Returns:
            list: Filtered signals
        """
        threshold = float(min_confidence)
        if 0 <= threshold <= 1:
            threshold *= 100.0

        return [s for s in signals if s.get('confidence', 0) >= threshold]

    def display_signals(self, signals: List[Dict], detailed: bool = False) -> None:
        """
        Display signals in readable format

        Args:
            signals: List of signals
            detailed: If True, show detailed analysis
        """
        print("\nBUY SIGNALS GENERATED")
        print("="*80)

        if not signals:
            print("No buy signals generated")
            return

        print("Sorted by rank score (confidence + risk/reward + catalyst quality)")
        for i, signal in enumerate(signals, 1):
            print(f"\n{i}. {signal['ticker']} - {signal['confidence_level']} confidence")
            print("-"*40)
            target_price = signal.get('risk_reward', {}).get('target_price', signal.get('target_price', 0.0))
            try:
                target_price_value = float(target_price)
            except (TypeError, ValueError):
                target_price_value = 0.0
            print(f"   Current Price:       ${signal['price']:.2f}")
            print(f"   Suggested Entry:     ${signal['suggested_entry']:.2f}")
            print(f"   Stop Loss:           ${signal['suggested_stop_loss']:.2f}")
            print(f"   Target (Pre-event):  ${target_price_value:.2f}")
            print(f"   Confidence Score:    {signal['confidence']:.1f}/100")
            ds = signal.get('distress_score', signal.get('triage_distress_score_used', ''))
            imp = signal.get('impact_score', signal.get('triage_impact_score_used', ''))
            if ds or imp:
                print(f"   Catalyst Quality:    distress {ds}/100, impact {imp}/100")
            print(f"   Risk/Reward Ratio:   {signal['risk_reward']['risk_reward_ratio']:.2f}:1")
            print(f"   Rank Score:          {compute_signal_rank_score(signal):.1f}")

            if detailed:
                print(f"\n   Reasons:")
                for reason in signal.get('reasons', []):
                    print(f"   - {reason}")


def main():
    """Test the signal generator"""
    generator = SignalGenerator()

    # Test analysis results
    test_analyses = [
        {
            'ticker': 'AAPL',
            'event_date': '2024-01-15',
            'pre_event_price': 180.0,
            'current_price': 160.0,
            'min_price_post_event': 158.0,
            'max_drop_pct': 12.2,
            'recovery_days': None,
            'current_rsi': 28.5,
            'rsi_oversold': True,
            'price_below_ma20': True,
            'volume_spike_at_event': 2.1
        },
        {
            'ticker': 'MSFT',
            'event_date': '2024-01-16',
            'pre_event_price': 380.0,
            'current_price': 365.0,
            'min_price_post_event': 362.0,
            'max_drop_pct': 4.7,
            'recovery_days': 2,
            'current_rsi': 35.2,
            'rsi_oversold': False,
            'price_below_ma20': False,
            'volume_spike_at_event': 1.3
        }
    ]

    # Generate signals
    signals = generator.generate_signals_batch(test_analyses)

    # Rank signals
    ranked = generator.rank_signals(signals)

    # Display
    generator.display_signals(ranked, detailed=True)


if __name__ == '__main__':
    main()
