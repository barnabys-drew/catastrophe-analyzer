"""
Database Manager Module
Manages CSV file storage and retrieval of breach and analysis data
"""

import csv
import os
from typing import List, Dict, Optional
from datetime import datetime
import json


class DatabaseManager:
    """
    Manages CSV-based persistence for breach analysis data
    """

    def __init__(self, data_dir: str = "../data"):
        """
        Initialize database manager

        Args:
            data_dir: Directory containing CSV files
        """
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Define file paths
        self.breaches_file = os.path.join(data_dir, 'breaches.csv')
        self.analysis_file = os.path.join(data_dir, 'analysis_results.csv')
        self.signals_file = os.path.join(data_dir, 'buy_signals.csv')
        self.watchlist_file = os.path.join(data_dir, 'breach_watchlist.csv')
        self.timeseries_file = os.path.join(data_dir, 'breach_price_timeseries.csv')

        # Initialize files if they don't exist
        self._initialize_files()

    def _initialize_files(self) -> None:
        """Create CSV files with headers if they don't exist"""
        # Breaches file
        if not os.path.exists(self.breaches_file):
            with open(self.breaches_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'date_found', 'company', 'ticker', 'breach_type', 'severity',
                    'source', 'url', 'summary', 'date_added'
                ])
                writer.writeheader()

        # Analysis results file
        if not os.path.exists(self.analysis_file):
            with open(self.analysis_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'breach_date', 'pre_breach_price', 'current_price',
                    'min_price_post_breach', 'max_drop_pct', 'recovery_days',
                    'current_rsi', 'volume_spike_at_breach', 'analysis_date'
                ])
                writer.writeheader()

        # Signals file
        if not os.path.exists(self.signals_file):
            with open(self.signals_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'signal_date', 'ticker', 'signal_type', 'confidence_level',
                    'confidence_score', 'entry_price', 'stop_loss', 'target_price',
                    'risk_reward_ratio', 'breach_date', 'executed', 'execution_price',
                    'execution_date', 'outcome'
                ])
                writer.writeheader()

        # Watchlist file (tracks companies whose stock gets monitored)
        if not os.path.exists(self.watchlist_file):
            with open(self.watchlist_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'company', 'breach_date', 'source', 'url',
                    'watch_start_date', 'last_checked_at',
                    'status',  # ACTIVE, SIGNAL_CREATED, EXPIRED
                    'timeseries_saved'  # Yes/No
                ])
                writer.writeheader()

        # Price timeseries file (before/after around breach date)
        if not os.path.exists(self.timeseries_file):
            with open(self.timeseries_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'breach_date', 'day_offset', 'date', 'close', 'volume'
                ])
                writer.writeheader()

    def add_breach(self, breach: Dict) -> bool:
        """
        Add a new breach record

        Args:
            breach: Breach data with keys: company, ticker, breach_type, severity, source, url, summary

        Returns:
            bool: True if successful
        """
        try:
            # Check if breach already exists
            if self._breach_exists(breach.get('ticker'), breach.get('date_found')):
                return False

            with open(self.breaches_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'date_found', 'company', 'ticker', 'breach_type', 'severity',
                    'source', 'url', 'summary', 'date_added'
                ])

                record = {
                    'date_found': breach.get('date_found', datetime.now().strftime('%Y-%m-%d')),
                    'company': breach.get('company', ''),
                    'ticker': breach.get('ticker', ''),
                    'breach_type': breach.get('breach_type', 'Unknown'),
                    'severity': breach.get('severity', 'Unknown'),
                    'source': breach.get('source', ''),
                    'url': breach.get('url', ''),
                    'summary': breach.get('summary', '')[:500],  # Limit summary
                    'date_added': datetime.now().isoformat()
                }

                writer.writerow(record)
            return True

        except Exception as e:
            print(f"Error adding breach: {e}")
            return False

    def _breach_exists(self, ticker: str, date_found: str) -> bool:
        """Check if a breach already exists"""
        if not os.path.exists(self.breaches_file):
            return False

        with open(self.breaches_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('ticker') == ticker and row.get('date_found') == date_found:
                    return True
        return False

    def add_analysis(self, analysis: Dict) -> bool:
        """
        Add analysis results

        Args:
            analysis: Analysis result dictionary from StockAnalyzer

        Returns:
            bool: True if successful
        """
        try:
            with open(self.analysis_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'breach_date', 'pre_breach_price', 'current_price',
                    'min_price_post_breach', 'max_drop_pct', 'recovery_days',
                    'current_rsi', 'volume_spike_at_breach', 'analysis_date'
                ])

                record = {
                    'ticker': analysis.get('ticker', ''),
                    'breach_date': analysis.get('breach_date', ''),
                    'pre_breach_price': analysis.get('pre_breach_price', ''),
                    'current_price': analysis.get('current_price', ''),
                    'min_price_post_breach': analysis.get('min_price_post_breach', ''),
                    'max_drop_pct': analysis.get('max_drop_pct', ''),
                    'recovery_days': analysis.get('recovery_days', ''),
                    'current_rsi': analysis.get('current_rsi', ''),
                    'volume_spike_at_breach': analysis.get('volume_spike_at_breach', ''),
                    'analysis_date': analysis.get('analysis_date', datetime.now().isoformat())
                }

                writer.writerow(record)
            return True

        except Exception as e:
            print(f"Error adding analysis: {e}")
            return False

    def add_signal(self, signal: Dict) -> bool:
        """
        Add a trading signal

        Args:
            signal: Signal data from SignalGenerator

        Returns:
            bool: True if successful
        """
        try:
            with open(self.signals_file, 'a', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'signal_date', 'ticker', 'signal_type', 'confidence_level',
                    'confidence_score', 'entry_price', 'stop_loss', 'target_price',
                    'risk_reward_ratio', 'breach_date', 'executed', 'execution_price',
                    'execution_date', 'outcome'
                ])

                record = {
                    'signal_date': signal.get('signal_date', datetime.now().isoformat()),
                    'ticker': signal.get('ticker', ''),
                    'signal_type': signal.get('signal_type', ''),
                    'confidence_level': signal.get('confidence_level', ''),
                    'confidence_score': signal.get('confidence', ''),
                    'entry_price': signal.get('suggested_entry', ''),
                    'stop_loss': signal.get('suggested_stop_loss', ''),
                    'target_price': signal.get('risk_reward', {}).get('target_price', ''),
                    'risk_reward_ratio': signal.get('risk_reward', {}).get('risk_reward_ratio', ''),
                    'breach_date': signal.get('breach_date', ''),
                    'executed': 'No',
                    'execution_price': '',
                    'execution_date': '',
                    'outcome': ''
                }

                writer.writerow(record)
            return True

        except Exception as e:
            print(f"Error adding signal: {e}")
            return False

    def _watch_exists(self, ticker: str, breach_date: str) -> bool:
        """Check if a watch already exists for (ticker, breach_date)."""
        if not os.path.exists(self.watchlist_file):
            return False
        with open(self.watchlist_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("ticker") == ticker and row.get("breach_date") == breach_date:
                    return True
        return False

    def add_watch_if_new(self, watch: Dict) -> bool:
        """
        Add a new breach watch record if one doesn't already exist.

        Args:
            watch: keys: ticker, company, breach_date, source, url
        """
        try:
            ticker = watch.get("ticker", "")
            breach_date = watch.get("breach_date", "")
            if not ticker or not breach_date:
                return False

            if self._watch_exists(ticker, breach_date):
                return False

            with open(self.watchlist_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'company', 'breach_date', 'source', 'url',
                    'watch_start_date', 'last_checked_at',
                    'status',
                    'timeseries_saved'
                ])
                writer.writerow({
                    'ticker': ticker,
                    'company': watch.get('company', ''),
                    'breach_date': breach_date,
                    'source': watch.get('source', ''),
                    'url': watch.get('url', ''),
                    'watch_start_date': watch.get('watch_start_date', datetime.now().strftime('%Y-%m-%d')),
                    'last_checked_at': watch.get('last_checked_at', datetime.now().isoformat()),
                    'status': watch.get('status', 'ACTIVE'),
                    'timeseries_saved': watch.get('timeseries_saved', 'No'),
                })

            return True
        except Exception as e:
            print(f"Error adding watch: {e}")
            return False

    def get_active_watches(self, max_days: int) -> List[Dict]:
        """
        Get active watches that are still within the monitoring window.
        """
        results: List[Dict] = []
        if not os.path.exists(self.watchlist_file):
            return results

        now = datetime.now()
        with open(self.watchlist_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = (row.get("status") or "").upper()
                if status not in ("ACTIVE", "SIGNAL_CREATED"):
                    continue

                breach_date = row.get("breach_date", "")
                try:
                    bd = datetime.strptime(breach_date, "%Y-%m-%d")
                except ValueError:
                    continue

                if (now - bd).days <= max_days:
                    row["status"] = status
                    results.append(row)

        return results

    def mark_watch_last_checked(self, ticker: str, breach_date: str) -> bool:
        """Update last_checked_at timestamp for a watch."""
        try:
            with open(self.watchlist_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            updated = False
            for r in rows:
                if r.get("ticker") == ticker and r.get("breach_date") == breach_date:
                    r["last_checked_at"] = datetime.now().isoformat()
                    updated = True

            if not updated:
                return False

            with open(self.watchlist_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            return True
        except Exception as e:
            print(f"Error updating watch timestamp: {e}")
            return False

    def mark_watch_signal_created(self, ticker: str, breach_date: str) -> bool:
        """Mark watch as having had a signal created."""
        return self._mark_watch_status(ticker, breach_date, "SIGNAL_CREATED")

    def update_watch_metadata(
        self,
        ticker: str,
        breach_date: str,
        company: Optional[str] = None,
        source: Optional[str] = None,
        url: Optional[str] = None,
    ) -> bool:
        """
        Update company/source/url metadata for an existing watch.

        Useful when canonical entity selection logic improves over time.
        """
        try:
            with open(self.watchlist_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            updated = False
            for r in rows:
                if r.get("ticker") == ticker and r.get("breach_date") == breach_date:
                    if company is not None:
                        r["company"] = company
                    if source is not None:
                        r["source"] = source
                    if url is not None:
                        r["url"] = url
                    updated = True

            if not updated:
                return False

            with open(self.watchlist_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except Exception as e:
            print(f"Error updating watch metadata: {e}")
            return False

    def mark_watch_expired(self, ticker: str, breach_date: str) -> bool:
        """Mark watch as expired."""
        return self._mark_watch_status(ticker, breach_date, "EXPIRED")

    def _mark_watch_status(self, ticker: str, breach_date: str, status: str) -> bool:
        try:
            with open(self.watchlist_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            updated = False
            for r in rows:
                if r.get("ticker") == ticker and r.get("breach_date") == breach_date:
                    r["status"] = status
                    updated = True

            if not updated:
                return False

            with open(self.watchlist_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)

            return True
        except Exception as e:
            print(f"Error updating watch status: {e}")
            return False

    def _timeseries_exists(self, ticker: str, breach_date: str) -> bool:
        if not os.path.exists(self.timeseries_file):
            return False
        with open(self.timeseries_file, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("ticker") == ticker and row.get("breach_date") == breach_date:
                    return True
        return False

    def mark_timeseries_saved(self, ticker: str, breach_date: str) -> bool:
        """Mark timeseries_saved=Yes in watchlist for (ticker, breach_date)."""
        try:
            with open(self.watchlist_file, "r", newline="") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames or []
                rows = list(reader)

            updated = False
            for r in rows:
                if r.get("ticker") == ticker and r.get("breach_date") == breach_date:
                    r["timeseries_saved"] = "Yes"
                    updated = True

            if not updated:
                return False

            with open(self.watchlist_file, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            return True
        except Exception as e:
            print(f"Error marking timeseries saved: {e}")
            return False

    def add_price_timeseries(self, rows: List[Dict]) -> bool:
        """
        Append price timeseries rows to breaches price timeseries file.
        """
        try:
            if not rows:
                return False
            # Idempotency: only append if first row set doesn't exist
            first = rows[0]
            ticker = first.get("ticker", "")
            breach_date = first.get("breach_date", "")
            if not ticker or not breach_date:
                return False
            if self._timeseries_exists(ticker, breach_date):
                return False

            with open(self.timeseries_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'ticker', 'breach_date', 'day_offset', 'date', 'close', 'volume'
                ])
                for r in rows:
                    writer.writerow({
                        'ticker': r.get('ticker', ''),
                        'breach_date': r.get('breach_date', ''),
                        'day_offset': r.get('day_offset', ''),
                        'date': r.get('date', ''),
                        'close': r.get('close', ''),
                        'volume': r.get('volume', ''),
                    })
            return True
        except Exception as e:
            print(f"Error adding price timeseries: {e}")
            return False

    def get_breaches(self, ticker: str = None) -> List[Dict]:
        """
        Get breach records

        Args:
            ticker: Optional filter by ticker

        Returns:
            list: Breach records
        """
        results = []

        if not os.path.exists(self.breaches_file):
            return results

        with open(self.breaches_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker is None or row.get('ticker') == ticker:
                    results.append(row)

        return results

    def get_analysis_history(self, ticker: str = None) -> List[Dict]:
        """
        Get analysis history

        Args:
            ticker: Optional filter by ticker

        Returns:
            list: Analysis records
        """
        results = []

        if not os.path.exists(self.analysis_file):
            return results

        with open(self.analysis_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker is None or row.get('ticker') == ticker:
                    results.append(row)

        return results

    def get_signals(self, ticker: str = None, executed_only: bool = False) -> List[Dict]:
        """
        Get trading signals

        Args:
            ticker: Optional filter by ticker
            executed_only: If True, only show executed signals

        Returns:
            list: Signal records
        """
        results = []

        if not os.path.exists(self.signals_file):
            return results

        with open(self.signals_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker and row.get('ticker') != ticker:
                    continue
                if executed_only and row.get('executed') != 'Yes':
                    continue
                results.append(row)

        return results

    def update_signal_execution(self, ticker: str, execution_price: float, 
                               execution_date: str = None) -> bool:
        """
        Update a signal as executed

        Args:
            ticker: Stock ticker
            execution_price: Price at which signal was executed
            execution_date: Date of execution

        Returns:
            bool: True if successful
        """
        if not execution_date:
            execution_date = datetime.now().strftime('%Y-%m-%d')

        # Read all signals
        signals = []
        with open(self.signals_file, 'r') as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            for row in reader:
                if row.get('ticker') == ticker and row.get('executed') != 'Yes':
                    row['executed'] = 'Yes'
                    row['execution_price'] = execution_price
                    row['execution_date'] = execution_date
                signals.append(row)

        # Write back
        try:
            with open(self.signals_file, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(signals)
            return True
        except Exception as e:
            print(f"Error updating signal: {e}")
            return False

    def get_statistics(self) -> Dict:
        """
        Get database statistics

        Returns:
            dict: Statistics about stored data
        """
        breaches = self.get_breaches()
        signals = self.get_signals()
        executed_signals = [s for s in signals if s.get('executed') == 'Yes']

        # Get unique tickers from signals
        signal_tickers = set(s.get('ticker') for s in signals)

        # Calculate win rate for executed signals
        winning_signals = len([s for s in executed_signals if s.get('outcome', '').lower() == 'win'])
        win_rate = (winning_signals / len(executed_signals) * 100) if executed_signals else 0

        return {
            'total_breaches': len(breaches),
            'total_signals': len(signals),
            'executed_signals': len(executed_signals),
            'unexecuted_signals': len(signals) - len(executed_signals),
            'signals_win_rate': f"{win_rate:.1f}%",
            'unique_tickers_in_signals': len(signal_tickers),
            'breaches_by_source': self._count_by_field(breaches, 'source'),
            'signals_by_confidence': self._count_by_field(signals, 'confidence_level')
        }

    def _count_by_field(self, records: List[Dict], field: str) -> Dict[str, int]:
        """Count records by field value"""
        counts = {}
        for record in records:
            value = record.get(field, 'Unknown')
            counts[value] = counts.get(value, 0) + 1
        return counts

    def display_statistics(self) -> None:
        """Display database statistics"""
        stats = self.get_statistics()

        print("\nDATABASE STATISTICS")
        print("="*60)
        print(f"Total breaches recorded:  {stats['total_breaches']}")
        print(f"Total signals generated:  {stats['total_signals']}")
        print(f"  - Executed:             {stats['executed_signals']}")
        print(f"  - Pending:              {stats['unexecuted_signals']}")
        print(f"Signals win rate:         {stats['signals_win_rate']}")
        print(f"Unique tickers:           {stats['unique_tickers_in_signals']}")

        if stats['breaches_by_source']:
            print(f"\nBreaches by source:")
            for source, count in stats['breaches_by_source'].items():
                print(f"  {source}: {count}")

        if stats['signals_by_confidence']:
            print(f"\nSignals by confidence:")
            for conf, count in stats['signals_by_confidence'].items():
                print(f"  {conf}: {count}")

    def export_to_json(self, filename: str = "breach_analysis.json") -> bool:
        """
        Export all data to JSON file

        Args:
            filename: Output filename

        Returns:
            bool: True if successful
        """
        try:
            data = {
                'breaches': self.get_breaches(),
                'analysis': self.get_analysis_history(),
                'signals': self.get_signals(),
                'statistics': self.get_statistics(),
                'exported': datetime.now().isoformat()
            }

            with open(filename, 'w') as f:
                json.dump(data, f, indent=2)

            print(f"Data exported to {filename}")
            return True

        except Exception as e:
            print(f"Error exporting data: {e}")
            return False


def main():
    """Test the database manager"""
    db = DatabaseManager()

    # Add sample data
    print("Adding sample data...")

    sample_breach = {
        'company': 'Acme Corp',
        'ticker': 'ACME',
        'date_found': '2024-01-15',
        'breach_type': 'Data Exfiltration',
        'severity': 'High',
        'source': 'BleepingComputer',
        'url': 'https://example.com/breach',
        'summary': 'Major breach affecting 100,000 users'
    }

    sample_analysis = {
        'ticker': 'ACME',
        'breach_date': '2024-01-15',
        'pre_breach_price': 50.0,
        'current_price': 42.0,
        'min_price_post_breach': 40.0,
        'max_drop_pct': 20.0,
        'recovery_days': None,
        'current_rsi': 28.5,
        'volume_spike_at_breach': 2.3
    }

    db.add_breach(sample_breach)
    db.add_analysis(sample_analysis)

    # Display statistics
    db.display_statistics()

    # Get records
    print("\n\nBREACHES:")
    for breach in db.get_breaches():
        print(f"  {breach['ticker']}: {breach['company']} ({breach['date_found']})")


if __name__ == '__main__':
    main()
