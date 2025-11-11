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

    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'signals': {
                'rsi_oversold_threshold': 30,
                'price_drop_threshold': 10,
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

        # Condition 1: RSI oversold OR recent significant drop
        rsi_oversold = analysis.get('rsi_oversold', False)
        significant_drop = analysis.get('max_drop_pct', 0) > drop_threshold

        # Condition 2: Volume spike at breach
        volume_spike = analysis.get('volume_spike_at_breach', 0) > volume_threshold

        # Determine if signal is generated
        generates_signal = (rsi_oversold or significant_drop) and volume_spike

        if not generates_signal:
            return None

        # Calculate confidence
        confidence_score = self._calculate_confidence(analysis)

        return {
            'ticker': ticker,
            'signal_type': 'BUY_OPPORTUNITY',
            'signal_date': datetime.now().isoformat(),
            'breach_date': analysis.get('breach_date'),
            'price': analysis.get('current_price'),
            'pre_breach_price': analysis.get('pre_breach_price'),
            'rsi': analysis.get('current_rsi'),
            'max_drop_pct': analysis.get('max_drop_pct'),
            'recovery_days': analysis.get('recovery_days'),
            'volume_spike': analysis.get('volume_spike_at_breach'),
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
        volume_spike = analysis.get('volume_spike_at_breach', 1.0)
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
        if score >= 70:
            return 'HIGH'
        elif score >= 40:
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

        if analysis.get('rsi_oversold'):
            reasons.append(f"RSI is {analysis.get('current_rsi'):.1f} (oversold)")

        drop_pct = analysis.get('max_drop_pct', 0)
        if drop_pct > 10:
            reasons.append(f"Stock dropped {drop_pct:.1f}% post-breach")

        volume_spike = analysis.get('volume_spike_at_breach', 1.0)
        reasons.append(f"Volume spike of {volume_spike:.1f}x at breach confirms selling pressure")

        if analysis.get('price_below_ma20'):
            reasons.append("Price is below 20-day moving average")

        recovery = analysis.get('recovery_days')
        if recovery is None:
            reasons.append("Stock has not yet recovered to pre-breach price")
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
        min_price = analysis.get('min_price_post_breach', current_price)

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
        min_price = analysis.get('min_price_post_breach', 0)
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
        pre_breach_price = analysis.get('pre_breach_price', current_price * 1.05)

        # Risk: from entry to stop loss
        risk = entry_price - stop_loss
        risk_pct = (risk / entry_price * 100) if entry_price > 0 else 0

        # Reward: from entry to pre-breach price (target)
        reward = pre_breach_price - entry_price
        reward_pct = (reward / entry_price * 100) if entry_price > 0 else 0

        # Risk/reward ratio
        ratio = reward / risk if risk > 0 else 0

        return {
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'target_price': pre_breach_price,
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
        threshold = min_confidence * 100

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
            print(f"   Target (Pre-breach): ${signal['suggested_entry'] + signal['risk_reward']['reward_pct']/100 * signal['suggested_entry']:.2f}")
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
            'breach_date': '2024-01-15',
            'pre_breach_price': 180.0,
            'current_price': 160.0,
            'min_price_post_breach': 158.0,
            'max_drop_pct': 12.2,
            'recovery_days': None,
            'current_rsi': 28.5,
            'rsi_oversold': True,
            'price_below_ma20': True,
            'volume_spike_at_breach': 2.1
        },
        {
            'ticker': 'MSFT',
            'breach_date': '2024-01-16',
            'pre_breach_price': 380.0,
            'current_price': 365.0,
            'min_price_post_breach': 362.0,
            'max_drop_pct': 4.7,
            'recovery_days': 2,
            'current_rsi': 35.2,
            'rsi_oversold': False,
            'price_below_ma20': False,
            'volume_spike_at_breach': 1.3
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
