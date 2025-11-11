"""
Stock Analyzer Module
Analyzes stock price movements around breach events
"""

from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
import json


class StockAnalyzer:
    """
    Analyzes stock price movements and technical indicators around breach events
    Supports both live and mock analysis for testing
    """

    def __init__(self, use_mock: bool = True):
        """
        Initialize stock analyzer

        Args:
            use_mock: If True, use mock data instead of yfinance (useful for testing)
        """
        self.use_mock = use_mock

        if not use_mock:
            try:
                import yfinance as yf
                self.yf = yf
            except ImportError:
                print("Warning: yfinance not installed. Falling back to mock data.")
                self.use_mock = True

    def _get_mock_price_history(self, ticker: str, days: int = 60) -> Dict:
        """
        Get mock price history for testing

        Args:
            ticker: Stock ticker
            days: Number of days of history

        Returns:
            dict: Mock historical data
        """
        # Generate mock data with realistic patterns
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        base_price = 150.0  # Start price
        prices = []
        volumes = []
        current_price = base_price

        for i in range(days):
            # Add some randomness
            change = (i % 3) * 0.5 - 0.75  # Small variations
            current_price += change

            # Create volume spike around day 20 (simulated breach)
            if 15 <= i <= 25:
                volume = 50000000 + (i - 15) * 5000000
            else:
                volume = 30000000 + (i % 10) * 1000000

            prices.append(current_price)
            volumes.append(volume)

        return {
            'ticker': ticker,
            'prices': prices,
            'volumes': volumes,
            'dates': [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(days)],
            'high': max(prices),
            'low': min(prices),
            'close': prices[-1],
            'volume': volumes[-1]
        }

    def get_price_history(self, ticker: str, days: int = 60) -> Optional[Dict]:
        """
        Get historical price data for a stock

        Args:
            ticker: Stock ticker symbol
            days: Number of days of history

        Returns:
            dict: Historical price data or None
        """
        if self.use_mock:
            return self._get_mock_price_history(ticker, days)

        try:
            stock = self.yf.Ticker(ticker)
            hist = stock.history(period=f"{days}d")

            if hist.empty:
                return None

            return {
                'ticker': ticker,
                'prices': hist['Close'].tolist(),
                'volumes': hist['Volume'].tolist(),
                'dates': [d.strftime('%Y-%m-%d') for d in hist.index],
                'high': float(hist['High'].max()),
                'low': float(hist['Low'].min()),
                'close': float(hist['Close'].iloc[-1]),
                'volume': float(hist['Volume'].iloc[-1])
            }
        except Exception as e:
            print(f"Error fetching data for {ticker}: {e}")
            return None

    def calculate_rsi(self, prices: List[float], period: int = 14) -> List[float]:
        """
        Calculate Relative Strength Index (RSI)

        Args:
            prices: List of prices
            period: RSI period (default 14)

        Returns:
            list: RSI values
        """
        if len(prices) < period:
            return [50] * len(prices)  # Return neutral RSI if insufficient data

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        rsi_values = []
        gains = []
        losses = []

        # Calculate initial average gain/loss
        initial_gains = [d if d > 0 else 0 for d in deltas[:period]]
        initial_losses = [-d if d < 0 else 0 for d in deltas[:period]]

        avg_gain = sum(initial_gains) / period
        avg_loss = sum(initial_losses) / period

        # Calculate RSI for first period
        if avg_loss == 0:
            rsi = 100 if avg_gain > 0 else 50
        else:
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))

        rsi_values = [50] * period  # RSI not defined before first period
        rsi_values.append(rsi)

        # Calculate RSI for remaining prices
        for i in range(period + 1, len(prices)):
            delta = prices[i] - prices[i-1]

            gain = delta if delta > 0 else 0
            loss = -delta if delta < 0 else 0

            avg_gain = ((avg_gain * (period - 1)) + gain) / period
            avg_loss = ((avg_loss * (period - 1)) + loss) / period

            if avg_loss == 0:
                rsi = 100 if avg_gain > 0 else 50
            else:
                rs = avg_gain / avg_loss
                rsi = 100 - (100 / (1 + rs))

            rsi_values.append(rsi)

        return rsi_values

    def calculate_moving_average(self, prices: List[float], period: int = 20) -> List[float]:
        """
        Calculate simple moving average

        Args:
            prices: List of prices
            period: Moving average period

        Returns:
            list: Moving average values
        """
        ma = []
        for i in range(len(prices)):
            if i < period - 1:
                ma.append(None)
            else:
                ma.append(sum(prices[i-period+1:i+1]) / period)
        return ma

    def calculate_volume_spike(self, volumes: List[float], period: int = 20) -> List[float]:
        """
        Calculate volume spike ratio (current volume / average volume)

        Args:
            volumes: List of volumes
            period: Period for average calculation

        Returns:
            list: Volume spike ratios
        """
        spikes = []
        for i in range(len(volumes)):
            if i < period - 1:
                spikes.append(1.0)
            else:
                avg_volume = sum(volumes[i-period+1:i+1]) / period
                spike = volumes[i] / avg_volume if avg_volume > 0 else 1.0
                spikes.append(spike)
        return spikes

    def analyze_breach_impact(self, ticker: str, breach_date: str) -> Dict:
        """
        Analyze stock price impact of a breach

        Args:
            ticker: Stock ticker
            breach_date: Date of breach (YYYY-MM-DD)

        Returns:
            dict: Analysis results including price drop %, recovery time
        """
        history = self.get_price_history(ticker, days=90)

        if not history:
            return {
                'ticker': ticker,
                'breach_date': breach_date,
                'error': 'Could not fetch price history'
            }

        prices = history['prices']
        dates = history['dates']
        volumes = history['volumes']

        # Find breach date index (approximate - use date closest to breach)
        breach_idx = None
        try:
            breach_datetime = datetime.strptime(breach_date, '%Y-%m-%d')
            for i, date_str in enumerate(dates):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj >= breach_datetime:
                    breach_idx = i
                    break
        except ValueError:
            breach_idx = len(prices) // 3  # Default to 1/3 through data

        if breach_idx is None:
            breach_idx = len(prices) // 3

        # Get price before breach
        pre_breach_price = prices[max(0, breach_idx - 5)]
        post_breach_prices = prices[breach_idx:min(breach_idx + 30, len(prices))]

        if not post_breach_prices:
            return {
                'ticker': ticker,
                'breach_date': breach_date,
                'error': 'No data after breach date'
            }

        # Calculate metrics
        min_price_after = min(post_breach_prices)
        max_drop_pct = ((pre_breach_price - min_price_after) / pre_breach_price) * 100

        # Time to recovery (days to get back above pre-breach price)
        recovery_days = None
        for i, price in enumerate(post_breach_prices):
            if price >= pre_breach_price:
                recovery_days = i
                break

        # Calculate technical indicators
        rsi = self.calculate_rsi(prices)
        ma20 = self.calculate_moving_average(prices, 20)
        volume_spikes = self.calculate_volume_spike(volumes)

        # Get current RSI
        current_rsi = rsi[-1] if rsi else 50

        # Volume spike at breach
        breach_volume_spike = volume_spikes[breach_idx] if breach_idx < len(volume_spikes) else 1.0

        return {
            'ticker': ticker,
            'breach_date': breach_date,
            'pre_breach_price': float(pre_breach_price),
            'current_price': float(prices[-1]),
            'min_price_post_breach': float(min_price_after),
            'max_drop_pct': float(max_drop_pct),
            'recovery_days': recovery_days,
            'current_rsi': float(current_rsi),
            'rsi_oversold': current_rsi < 30,
            'price_below_ma20': (prices[-1] < ma20[-1]) if ma20[-1] else None,
            'volume_spike_at_breach': float(breach_volume_spike),
            'analysis_date': datetime.now().isoformat()
        }

    def batch_analyze(self, companies: List[Dict], breach_date: str = None) -> List[Dict]:
        """
        Analyze multiple companies

        Args:
            companies: List of company dicts with 'ticker' key
            breach_date: Date of breach event

        Returns:
            list: Analysis results for each company
        """
        results = []

        for company in companies:
            ticker = company.get('ticker') or company.get('company')
            if ticker:
                analysis = self.analyze_breach_impact(ticker, breach_date or '2024-01-01')
                results.append(analysis)

        return results

    def display_analysis(self, analysis_results: List[Dict]) -> None:
        """
        Display analysis results in readable format

        Args:
            analysis_results: List of analysis result dictionaries
        """
        print("\nSTOCK ANALYSIS RESULTS")
        print("="*80)

        for result in analysis_results:
            if 'error' in result:
                print(f"\n{result.get('ticker', 'UNKNOWN')}: {result['error']}")
                continue

            print(f"\n{result['ticker']} - Breach: {result['breach_date']}")
            print("-"*40)
            print(f"Pre-breach price:    ${result['pre_breach_price']:.2f}")
            print(f"Current price:       ${result['current_price']:.2f}")
            print(f"Lowest post-breach:  ${result['min_price_post_breach']:.2f}")
            print(f"Max drop:            {result['max_drop_pct']:.2f}%")
            print(f"Recovery time:       {result['recovery_days']} days" if result['recovery_days'] else "No recovery yet")
            print(f"Current RSI:         {result['current_rsi']:.2f}", end="")
            if result['rsi_oversold']:
                print(" (OVERSOLD)")
            else:
                print()
            print(f"Below 20-day MA:     {'Yes' if result['price_below_ma20'] else 'No'}")
            print(f"Breach volume spike: {result['volume_spike_at_breach']:.2f}x")


def main():
    """Test the analyzer"""
    analyzer = StockAnalyzer(use_mock=True)

    # Test companies
    test_companies = [
        {'ticker': 'AAPL', 'company': 'Apple'},
        {'ticker': 'MSFT', 'company': 'Microsoft'},
        {'ticker': 'CSCO', 'company': 'Cisco'},
    ]

    # Analyze
    results = analyzer.batch_analyze(test_companies, breach_date='2024-01-15')

    # Display
    analyzer.display_analysis(results)


if __name__ == '__main__':
    main()
