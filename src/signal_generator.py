"""
Signal Generator Module
Generates buy/sell signals based on breach analysis
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime
import json


class SignalGenerator:
    """
    Generates trading signals based on breach events and stock analysis
    """

    def __init__(self, config_path: str = "../config/settings.json"):
        """
        Initialize signal generator with configuration

        Args:
            config_path: Path to settings.json
        """
        try:
            with open(config_path, 'r') as f:
                self.config = json.load(f)
        except FileNotFoundError:
            self.config = self._get_default_config()

        self.signal_config = self.config.get('signals', {})

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

    def generate_buy_signal(self, analysis: Dict) -> Optional[Dict]:
        """
        Generate a buy signal from breach analysis

        Conditions:
        1. Stock is oversold (RSI < 30) OR recently had significant drop
        2. There was volume spike at breach
        3. Not in recovery phase yet (optional)

        Args:
            analysis: Stock analysis result from StockAnalyzer

        Returns:
            dict: Signal if conditions met, None otherwise
        """
        if 'error' in analysis:
            return None

        ticker = analysis.get('ticker')
        rsi_threshold = self.signal_config.get('rsi_oversold_threshold', 30)
        drop_threshold = self.signal_config.get('price_drop_threshold', 10)
        volume_threshold = self.signal_config.get('volume_spike_threshold', 1.5)
        require_drop_48h = bool(self.signal_config.get('require_drop_within_48h', True))
        drop_48h_threshold = float(self.signal_config.get('drop_within_48h_threshold', 1.0))

        # Condition 1: significant event-aligned dislocation and weak technical posture
        rsi_value = analysis.get("event_rsi", analysis.get("current_rsi", 50))
        rsi_oversold = analysis.get('rsi_oversold', rsi_value < rsi_threshold)
        significant_drop = analysis.get('max_drop_pct', 0) >= drop_threshold
        drop_48h_pct = float(analysis.get('drop_48h_pct', analysis.get('max_drop_pct', 0.0)))
        dropped_within_48h = drop_48h_pct >= drop_48h_threshold
        below_ma = bool(analysis.get('price_below_ma20'))

        # Condition 2: Volume spike at event
        volume_spike_at_event = analysis.get('volume_spike_at_event', analysis.get('volume_spike_at_breach', 0))
        volume_spike = volume_spike_at_event > volume_threshold

        # Condition 3: Event has not fully recovered too quickly (avoid chasing stale rebounds)
        recovery_days_threshold = int(self.signal_config.get('recovery_days_threshold', 5))
        recovery_days = analysis.get('recovery_days')
        not_recovered_too_quickly = recovery_days is None or recovery_days >= recovery_days_threshold

        # Determine if signal is generated (strict mode: require drop + volume + technical weakness)
        generates_signal = (
            significant_drop
            and (dropped_within_48h or not require_drop_48h)
            and volume_spike
            and (rsi_oversold or below_ma)
            and not_recovered_too_quickly
        )

        if not generates_signal:
            return None

        # Calculate confidence
        confidence_score = self._calculate_confidence(analysis)

        return {
            'ticker': ticker,
            'signal_type': 'BUY_OPPORTUNITY',
            'signal_date': datetime.now().isoformat(),
            'event_date': analysis.get('event_date', analysis.get('breach_date')),
            'breach_date': analysis.get('event_date', analysis.get('breach_date')),  # Legacy compatibility
            'event_category': analysis.get('event_category', ''),
            'price': analysis.get('current_price'),
            'pre_event_price': analysis.get('pre_event_price', analysis.get('pre_breach_price')),
            'pre_breach_price': analysis.get('pre_event_price', analysis.get('pre_breach_price')),  # Legacy compatibility
            'rsi': analysis.get('event_rsi', analysis.get('current_rsi')),
            'max_drop_pct': analysis.get('max_drop_pct'),
            'drop_48h_pct': drop_48h_pct,
            'recovery_days': analysis.get('recovery_days'),
            'volume_spike_at_event': volume_spike_at_event,
            'volume_spike': volume_spike_at_event,
            'confidence': confidence_score,
            'confidence_level': self._get_confidence_level(confidence_score),
            'reasons': self._generate_reasons(analysis),
            'suggested_entry': self._calculate_entry_price(analysis),
            'suggested_stop_loss': self._calculate_stop_loss(analysis),
            'risk_reward': self._calculate_risk_reward(analysis)
        }

    def _calculate_confidence(self, analysis: Dict) -> float:
        """
        Calculate confidence score 0-100

        Args:
            analysis: Stock analysis result

        Returns:
            float: Confidence score
        """
        score = 0

        # RSI oversold is strong signal (25 points)
        if analysis.get('rsi_oversold'):
            score += 25

        # Significant drop is good signal (20 points)
        drop_pct = analysis.get('max_drop_pct', 0)
        if drop_pct > 10:
            score += 20
        elif drop_pct > 5:
            score += 10

        # Volume spike confirms selling pressure (20 points)
        volume_spike = analysis.get('volume_spike_at_event', analysis.get('volume_spike_at_breach', 1.0))
        if volume_spike > 2.0:
            score += 20
        elif volume_spike > 1.5:
            score += 10

        # Below moving average is good (15 points)
        if analysis.get('price_below_ma20'):
            score += 15

        # Recently breached (recovery_days is None or small) (20 points)
        recovery = analysis.get('recovery_days')
        if recovery is None:
            score += 20
        elif recovery < 3:
            score += 10

        return min(score, 100)

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
        Suggest stop loss price (below the minimum)

        Args:
            analysis: Stock analysis result

        Returns:
            float: Suggested stop loss price
        """
        min_price = analysis.get('min_price_post_event', analysis.get('min_price_post_breach', 0))
        # Stop loss 3% below minimum
        return min_price * 0.97

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
        pre_event_price = analysis.get('pre_event_price', analysis.get('pre_breach_price', current_price * 1.05))

        # Risk: from entry to stop loss
        risk = entry_price - stop_loss
        risk_pct = (risk / entry_price * 100) if entry_price > 0 else 0

        # Reward: from entry to pre-event price (target)
        reward = pre_event_price - entry_price
        reward_pct = (reward / entry_price * 100) if entry_price > 0 else 0

        # Risk/reward ratio
        ratio = reward / risk if risk > 0 else 0

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target_price': pre_event_price,
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

    def rank_signals(self, signals: List[Dict]) -> List[Dict]:
        """
        Rank signals by attractiveness

        Args:
            signals: List of generated signals

        Returns:
            list: Signals sorted by quality (best first)
        """
        def score_signal(signal):
            confidence = signal.get('confidence', 0)
            risk_reward = signal.get('risk_reward', {}).get('risk_reward_ratio', 0)

            # Combine confidence and risk/reward
            combined_score = (confidence * 0.6) + (min(risk_reward, 5) * 12)  # Cap risk/reward at 5

            return combined_score

        return sorted(signals, key=score_signal, reverse=True)

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

        for i, signal in enumerate(signals, 1):
            print(f"\n{i}. {signal['ticker']} - {signal['confidence_level']} confidence")
            print("-"*40)
            print(f"   Current Price:       ${signal['price']:.2f}")
            print(f"   Suggested Entry:     ${signal['suggested_entry']:.2f}")
            print(f"   Stop Loss:           ${signal['suggested_stop_loss']:.2f}")
            print(f"   Target (Pre-event):  ${signal['suggested_entry'] + signal['risk_reward']['reward_pct']/100 * signal['suggested_entry']:.2f}")
            print(f"   Confidence Score:    {signal['confidence']:.1f}/100")
            print(f"   Risk/Reward Ratio:   {signal['risk_reward']['risk_reward_ratio']:.2f}:1")

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
