"""
Stock Analyzer Module
Analyzes stock price movements around breach events
"""

from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta, date
import os
import re

import requests


class StockAnalyzer:
    """
    Analyzes stock price movements and technical indicators around breach events
    Supports both live and mock analysis for testing
    """

    def __init__(self, use_mock: bool = True, stock_analysis_config: Optional[Dict[str, Any]] = None):
        """
        Initialize stock analyzer

        Args:
            use_mock: If True, use mock data instead of live market data (useful for testing)
            stock_analysis_config: Optional `stock_analysis` block from settings.json (data_source, etc.)
        """
        self.use_mock = use_mock
        self._stock_cfg: Dict[str, Any] = dict(stock_analysis_config or {})
        # Cache tradable checks so repeated watch cycles do not re-query bad symbols.
        self._tradable_cache: Dict[str, bool] = {}

        cfg_source = (self._stock_cfg.get("data_source") or "yfinance").strip().lower()
        token_env = (self._stock_cfg.get("tiingo_token_env") or "TIINGO_API_TOKEN").strip()
        self._tiingo_token_env = token_env
        self._tiingo_token: str = ""
        self._live_data_source = "yfinance"
        self.yf = None

        if not use_mock:
            if cfg_source == "tiingo":
                self._tiingo_token = os.environ.get(token_env, "").strip()
                if self._tiingo_token:
                    self._live_data_source = "tiingo"
                else:
                    print(
                        f"Warning: stock_analysis.data_source is tiingo but {token_env} is unset; "
                        "using yfinance."
                    )
                    self._live_data_source = "yfinance"
            elif cfg_source not in ("yfinance", "yahoo", ""):
                print(f"Warning: unknown stock_analysis.data_source {cfg_source!r}; using yfinance.")

            if self._live_data_source == "yfinance":
                try:
                    import yfinance as yf

                    self.yf = yf
                except ImportError:
                    print("Warning: yfinance not installed. Falling back to mock data.")
                    self.use_mock = True

    @staticmethod
    def _is_supported_symbol_format(ticker: str) -> bool:
        """
        Fast symbol gate for likely US-tradable equities.

        Accepts:
        - 1-5 uppercase letters (AAPL, BRK)
        - optional share class suffix .A (BRK.A)
        Rejects symbols with numeric-heavy/foreign suffix formats.
        """
        if not ticker:
            return False
        symbol = ticker.upper().strip()
        if "." in symbol:
            return bool(re.match(r"^[A-Z]{1,5}\.[A-Z]$", symbol))
        return bool(re.match(r"^[A-Z]{1,5}$", symbol))

    def validate_tradable_ticker(self, ticker: str) -> bool:
        """
        Determine whether ticker appears tradable for live analysis.

        In live mode, this performs a lightweight market-data check with a short
        lookback and caches the result.
        """
        symbol = (ticker or "").upper().strip()
        if not symbol:
            return False

        cached = self._tradable_cache.get(symbol)
        if cached is not None:
            return cached

        if not self._is_supported_symbol_format(symbol):
            self._tradable_cache[symbol] = False
            return False

        if self.use_mock:
            self._tradable_cache[symbol] = True
            return True

        if self._live_data_source == "tiingo":
            end_d = datetime.now().date()
            start_d = end_d - timedelta(days=14)
            rows = self._tiingo_fetch_daily(symbol, start_d, end_d)
            is_tradable = bool(rows)
            self._tradable_cache[symbol] = is_tradable
            return is_tradable

        try:
            stock = self.yf.Ticker(symbol)
            # Small probe before full analysis history request.
            probe = stock.history(period="5d")
            is_tradable = not probe.empty
            self._tradable_cache[symbol] = is_tradable
            return is_tradable
        except Exception:
            self._tradable_cache[symbol] = False
            return False

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
        symbol = (ticker or "").upper().strip()
        if not self.validate_tradable_ticker(symbol):
            return None

        if self.use_mock:
            return self._get_mock_price_history(symbol, days)

        if self._live_data_source == "tiingo":
            return self._get_tiingo_price_history(symbol, days)

        try:
            stock = self.yf.Ticker(symbol)
            hist = stock.history(period=f"{days}d")

            if hist.empty:
                self._tradable_cache[symbol] = False
                return None

            return {
                'ticker': symbol,
                'prices': hist['Close'].tolist(),
                'volumes': hist['Volume'].tolist(),
                'dates': [d.strftime('%Y-%m-%d') for d in hist.index],
                'high': float(hist['High'].max()),
                'low': float(hist['Low'].min()),
                'close': float(hist['Close'].iloc[-1]),
                'volume': float(hist['Volume'].iloc[-1])
            }
        except Exception as e:
            self._tradable_cache[symbol] = False
            print(f"Error fetching data for {symbol}: {e}")
            return None

    def _tiingo_fetch_daily(self, symbol: str, start_d: date, end_d: date) -> Optional[List[Dict[str, Any]]]:
        """Return Tiingo EOD rows (sorted ascending by date) or None on transport/API failure."""
        if not self._tiingo_token:
            return None
        url = f"https://api.tiingo.com/tiingo/daily/{symbol}/prices"
        params = {"startDate": start_d.isoformat(), "endDate": end_d.isoformat()}
        headers = {"Authorization": f"Token {self._tiingo_token}"}
        try:
            r = requests.get(url, params=params, headers=headers, timeout=30)
            if r.status_code == 404:
                return []
            if r.status_code != 200:
                print(f"Tiingo API HTTP {r.status_code} for {symbol}: {r.text[:240]}")
                return None
            data = r.json()
            if not isinstance(data, list):
                return None
            return sorted(data, key=lambda row: str(row.get("date", "")))
        except Exception as exc:
            print(f"Tiingo request failed for {symbol}: {exc}")
            return None

    @staticmethod
    def _tiingo_row_date_str(row: Dict[str, Any]) -> str:
        raw = str(row.get("date", "") or "")
        if "T" in raw:
            return raw.split("T", 1)[0]
        return raw[:10]

    def _tiingo_rows_to_history(self, symbol: str, rows: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not rows:
            return None
        dates: List[str] = []
        prices: List[float] = []
        volumes: List[float] = []
        highs: List[float] = []
        lows: List[float] = []
        for row in rows:
            dt = self._tiingo_row_date_str(row)
            if not dt:
                continue
            close = row.get("adjClose")
            if close is None:
                close = row.get("close")
            if close is None:
                continue
            vol = row.get("adjVolume", row.get("volume", 0))
            if vol is None:
                vol = 0
            hi = row.get("high", close)
            lo = row.get("low", close)
            dates.append(dt)
            prices.append(float(close))
            volumes.append(float(vol))
            highs.append(float(hi if hi is not None else close))
            lows.append(float(lo if lo is not None else close))
        if not prices:
            return None
        return {
            "ticker": symbol,
            "prices": prices,
            "volumes": volumes,
            "dates": dates,
            "high": max(highs),
            "low": min(lows),
            "close": float(prices[-1]),
            "volume": float(volumes[-1]),
        }

    def _get_tiingo_price_history(self, symbol: str, days: int) -> Optional[Dict[str, Any]]:
        end_d = datetime.now().date()
        calendar_span = max(int(days * 1.75) + 5, days + 20)
        start_d = end_d - timedelta(days=calendar_span)
        rows = self._tiingo_fetch_daily(symbol, start_d, end_d)
        if rows is None:
            self._tradable_cache[symbol] = False
            return None
        history = self._tiingo_rows_to_history(symbol, rows)
        if not history:
            self._tradable_cache[symbol] = False
            return None
        return history

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

    def analyze_event_impact(self, ticker: str, event_date: str, event_category: Optional[str] = None) -> Dict:
        """
        Analyze stock price impact of an event.

        Args:
            ticker: Stock ticker
            event_date: Date of event (YYYY-MM-DD)
            event_category: Optional event category for downstream consumers

        Returns:
            dict: Analysis results including price drop %, recovery time
        """
        history = self.get_price_history(ticker, days=90)

        if not history:
            return {
                'ticker': ticker,
                'event_date': event_date,
                'breach_date': event_date,  # Legacy compatibility
                'event_category': event_category or '',
                'error': 'Could not fetch price history'
            }

        prices = history['prices']
        dates = history['dates']
        volumes = history['volumes']

        _error_base = {
            'ticker': ticker,
            'event_date': event_date,
            'breach_date': event_date,
            'event_category': event_category or '',
        }

        event_idx = None
        try:
            event_datetime = datetime.strptime(event_date, '%Y-%m-%d')
            for i, date_str in enumerate(dates):
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                if date_obj >= event_datetime:
                    event_idx = i
                    break
        except ValueError:
            return {**_error_base, 'error': 'Unparseable event_date'}

        if event_idx is None:
            return {**_error_base, 'error': 'Event date is after all available price data'}

        min_post_bars = 3
        if event_idx >= len(prices) - min_post_bars:
            return {**_error_base, 'error': 'Not enough post-event price data'}

        if event_idx == 0:
            return {**_error_base, 'error': 'No pre-event price data (event on first available bar)'}

        pre_event_price = prices[event_idx - 1]
        event_anchor_price = prices[event_idx]
        post_event_analysis_days = int(self._stock_cfg.get('post_event_analysis_days', 10))
        post_event_prices = prices[event_idx:min(event_idx + post_event_analysis_days, len(prices))]

        if not post_event_prices:
            return {**_error_base, 'error': 'No data after event date'}

        min_price_after = min(post_event_prices)
        max_drop_pct = (
            ((pre_event_price - min_price_after) / pre_event_price) * 100
            if pre_event_price > 0 else 0.0
        )

        # 48-hour post-event dislocation (approx. 2 trading days after event anchor).
        post_event_window_days = 2
        window_end = min(len(prices), event_idx + post_event_window_days + 1)
        post_48h_prices = prices[event_idx:window_end]
        min_price_48h = min(post_48h_prices) if post_48h_prices else event_anchor_price
        drop_48h_pct = (
            ((event_anchor_price - min_price_48h) / event_anchor_price) * 100
            if event_anchor_price > 0
            else 0.0
        )

        # Time to recovery (days to get back above pre-event price)
        recovery_days = None
        for i, price in enumerate(post_event_prices):
            if price >= pre_event_price:
                recovery_days = i
                break

        # Calculate technical indicators
        rsi = self.calculate_rsi(prices)
        ma20 = self.calculate_moving_average(prices, 20)
        volume_spikes = self.calculate_volume_spike(volumes)

        # Use event-window RSI for event-driven signal gating; keep current RSI for display/diagnostics.
        current_rsi = rsi[-1] if rsi else 50
        event_rsi = rsi[event_idx] if event_idx < len(rsi) else current_rsi

        # Volume spike at event
        event_volume_spike = volume_spikes[event_idx] if event_idx < len(volume_spikes) else 1.0
        trailing_volume_window = volumes[-20:] if len(volumes) >= 20 else volumes
        avg_volume_20d = (
            (sum(trailing_volume_window) / len(trailing_volume_window))
            if trailing_volume_window
            else 0.0
        )

        return {
            'ticker': ticker,
            'event_date': event_date,
            'breach_date': event_date,  # Legacy compatibility
            'event_category': event_category or '',
            'pre_event_price': float(pre_event_price),
            'pre_breach_price': float(pre_event_price),  # Legacy compatibility
            'event_anchor_price': float(event_anchor_price),
            'current_price': float(prices[-1]),
            'min_price_post_event': float(min_price_after),
            'min_price_post_breach': float(min_price_after),  # Legacy compatibility
            'max_drop_pct': float(max_drop_pct),
            'post_event_window_days': int(post_event_window_days),
            'min_price_post_event_48h': float(min_price_48h),
            'drop_48h_pct': float(drop_48h_pct),
            'recovery_days': recovery_days,
            'current_rsi': float(current_rsi),
            'event_rsi': float(event_rsi),
            'rsi_oversold': event_rsi < 30,
            'price_below_ma20': (prices[-1] < ma20[-1]) if ma20[-1] else None,
            'volume_spike_at_event': float(event_volume_spike),
            'volume_spike_at_breach': float(event_volume_spike),  # Legacy compatibility
            'avg_volume_20d': float(avg_volume_20d),
            'analysis_date': datetime.now().isoformat()
        }

    # Backward-compatible alias while callers migrate.
    def analyze_breach_impact(self, ticker: str, breach_date: str, event_category: Optional[str] = None) -> Dict:
        return self.analyze_event_impact(ticker=ticker, event_date=breach_date, event_category=event_category)

    def get_event_price_series(
        self,
        ticker: str,
        event_date: str,
        pre_days: int = 30,
        post_days: int = 30,
    ) -> List[Dict]:
        """
        Return before/after daily price series around event_date.

        Day offsets are based on trading-day index positions from the fetched history.
        - day_offset < 0: before event
        - day_offset == 0: first date >= event_date (approx)
        - day_offset > 0: after event
        """
        # Fetch enough trading days to cover pre+post
        history_days = max(90, pre_days + post_days + 10)
        history = self.get_price_history(ticker, days=history_days)
        if not history:
            return []

        prices = history["prices"]
        dates = history["dates"]
        volumes = history["volumes"]

        event_idx = None
        try:
            event_datetime = datetime.strptime(event_date, "%Y-%m-%d")
            for i, date_str in enumerate(dates):
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                if date_obj >= event_datetime:
                    event_idx = i
                    break
        except ValueError:
            event_idx = len(prices) // 3

        if event_idx is None:
            event_idx = len(prices) // 3

        pre_start = max(0, event_idx - pre_days)
        pre_end = event_idx  # exclusive
        post_start = event_idx
        post_end = min(len(prices), event_idx + post_days)

        rows: List[Dict] = []

        # Pre-event: offsets are negative
        pre_len = pre_end - pre_start
        for j in range(pre_len):
            idx = pre_start + j
            day_offset = j - pre_len  # e.g. -pre_len..-1
            rows.append({
                "ticker": ticker,
                "event_date": event_date,
                "breach_date": event_date,  # Legacy compatibility
                "day_offset": day_offset,
                "date": dates[idx],
                "close": float(prices[idx]),
                "volume": float(volumes[idx]) if idx < len(volumes) else "",
            })

        # Post-event: offsets are >= 0
        for idx in range(post_start, post_end):
            rows.append({
                "ticker": ticker,
                "event_date": event_date,
                "breach_date": event_date,  # Legacy compatibility
                "day_offset": idx - event_idx,
                "date": dates[idx],
                "close": float(prices[idx]),
                "volume": float(volumes[idx]) if idx < len(volumes) else "",
            })

        return rows

    # Backward-compatible alias while callers migrate.
    def get_breach_price_series(
        self,
        ticker: str,
        breach_date: str,
        pre_days: int = 30,
        post_days: int = 30,
    ) -> List[Dict]:
        return self.get_event_price_series(
            ticker=ticker,
            event_date=breach_date,
            pre_days=pre_days,
            post_days=post_days,
        )

    def batch_analyze(self, companies: List[Dict], event_date: str = None, breach_date: str = None) -> List[Dict]:
        """
        Analyze multiple companies

        Args:
            companies: List of company dicts with 'ticker' key
            event_date: Date of event
            breach_date: Deprecated alias for event_date

        Returns:
            list: Analysis results for each company
        """
        results = []

        for company in companies:
            ticker = company.get('ticker') or company.get('company')
            if ticker:
                symbol = (ticker or "").upper().strip()
                # Allow per-company event_date override (useful for automated pipelines)
                per_company_event_date = None
                event_category = None
                if isinstance(company, dict):
                    per_company_event_date = company.get('event_date') or company.get('breach_date')
                    event_category = company.get('event_category')

                effective_event_date = per_company_event_date or event_date or breach_date or '2024-01-01'
                if not self.validate_tradable_ticker(symbol):
                    results.append(
                        {
                            "ticker": symbol or ticker,
                            "event_date": effective_event_date,
                            "breach_date": effective_event_date,
                            "event_category": event_category or "",
                            "error": "Ticker failed tradable validation gate",
                        }
                    )
                    continue
                analysis = self.analyze_event_impact(
                    ticker=symbol,
                    event_date=effective_event_date,
                    event_category=event_category,
                )
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

            print(f"\n{result['ticker']} - Event: {result.get('event_date', result.get('breach_date'))}")
            print("-"*40)
            print(f"Pre-event price:     ${result.get('pre_event_price', result.get('pre_breach_price', 0.0)):.2f}")
            print(f"Current price:       ${result['current_price']:.2f}")
            print(f"Lowest post-event:   ${result.get('min_price_post_event', result.get('min_price_post_breach', 0.0)):.2f}")
            print(f"Max drop:            {result['max_drop_pct']:.2f}%")
            print(f"Recovery time:       {result['recovery_days']} days" if result['recovery_days'] else "No recovery yet")
            print(f"Current RSI:         {result['current_rsi']:.2f}", end="")
            if result['rsi_oversold']:
                print(" (OVERSOLD)")
            else:
                print()
            print(f"Below 20-day MA:     {'Yes' if result['price_below_ma20'] else 'No'}")
            print(f"Event volume spike:  {result.get('volume_spike_at_event', result.get('volume_spike_at_breach', 0.0)):.2f}x")


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
    results = analyzer.batch_analyze(test_companies, event_date='2024-01-15')

    # Display
    analyzer.display_analysis(results)


if __name__ == '__main__':
    main()
