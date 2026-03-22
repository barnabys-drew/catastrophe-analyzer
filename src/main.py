"""
Catastrophe Analyzer - Main CLI Interface
Orchestrates news scraping, entity extraction, stock analysis, and signal generation
"""

import sys
import os
from datetime import datetime
import json
import io
import contextlib
from email.utils import parsedate_to_datetime
from typing import Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_scraper import NewsScraper
from entity_extractor import EntityExtractor
from stock_analyzer import StockAnalyzer
from signal_generator import SignalGenerator
from database_manager import DatabaseManager


class CatastropheAnalyzerApp:
    """
    Main application orchestrating all modules
    """

    def __init__(self):
        """Initialize all components"""
        self.repo_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
        self.config_path = os.path.join(self.repo_root, 'config', 'settings.json')
        self.data_dir = os.path.join(self.repo_root, 'data')

        self.settings = self._load_settings()

        mock_env = os.environ.get("CATASTROPHE_ANALYZER_USE_MOCK_DATA", "").strip()
        if mock_env == "":
            mock_env = os.environ.get("BREACH_ANALYZER_USE_MOCK_DATA", "").strip()

        self.news_scraper = NewsScraper(config_path=self.config_path)
        self.entity_extractor = EntityExtractor(config_path=self.config_path)
        self.stock_analyzer = StockAnalyzer(
            use_mock=(
                mock_env.lower() in ["1", "true", "yes"]
                if mock_env != ""
                else self.settings.get('stock_analysis', {}).get('use_mock_data', True)
            )
        )
        self.signal_generator = SignalGenerator(config_path=self.config_path)
        self.db = DatabaseManager(data_dir=self.data_dir)

        self.current_articles = []
        self.current_entities = []
        self.current_analyses = []
        self.current_signals = []

    def _load_settings(self) -> Dict:
        """Load settings.json with safe defaults."""
        defaults = {}
        try:
            with open(self.config_path, 'r') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return defaults

    def display_menu(self) -> None:
        """Display main menu"""
        print("\n" + "="*80)
        print("CATASTROPHE ANALYZER - Cyber Security Event & Stock Opportunity Detection")
        print("="*80)
        print("\n1. Scan for breaches (update news sources)")
        print("2. Analyze recent breaches (extract entities & stock data)")
        print("3. Generate buy signals (from analysis)")
        print("4. View signal history")
        print("5. View breach history")
        print("6. Database statistics")
        print("7. Settings & configuration")
        print("8. Exit\n")

    def run(self) -> None:
        """Run the application"""
        print("\n" + "="*80)
        print("CATASTROPHE ANALYZER - Starting")
        print("="*80)

        while True:
            self.display_menu()
            choice = input("Enter choice (1-8): ").strip()

            if choice == '1':
                self.scan_breaches()
            elif choice == '2':
                self.analyze_breaches()
            elif choice == '3':
                self.generate_signals()
            elif choice == '4':
                self.view_signals()
            elif choice == '5':
                self.view_breaches()
            elif choice == '6':
                self.show_statistics()
            elif choice == '7':
                self.settings_menu()
            elif choice == '8':
                print("\nExiting Catastrophe Analyzer. Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")

    def _parse_published_date(self, published: str, fallback_date: str) -> str:
        """Parse RSS published string into YYYY-MM-DD."""
        if not published or published == 'Unknown':
            return fallback_date

        try:
            # Handles RFC2822 timestamps like "Mon, 18 Mar 2026 11:00:00 GMT"
            dt = parsedate_to_datetime(published)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            pass

        try:
            # Handles ISO timestamps
            s = (published or '').replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            return dt.strftime('%Y-%m-%d')
        except Exception:
            return fallback_date

    def _classify_breach_type_and_severity(self, title: str, summary: str) -> tuple:
        """Heuristic breach type + severity. Used for persistence/alert context only."""
        content = f"{title} {summary}".lower()

        breach_type = 'Security Incident'
        if 'ransomware' in content:
            breach_type = 'Ransomware'
        elif 'credential' in content or 'credentials leaked' in content:
            breach_type = 'Credential Leak'
        elif 'zero-day' in content or 'zero day' in content:
            breach_type = 'Zero-Day Vulnerability'
        elif 'exploit' in content:
            breach_type = 'Exploit'
        elif 'vulnerability' in content:
            breach_type = 'Vulnerability'
        elif 'data exposure' in content or 'data breach' in content or 'data leak' in content:
            breach_type = 'Data Breach'

        severity = 'Medium'
        critical_markers = ['ransomware', 'zero-day', 'zero day', 'critical', 'exploit', 'credential', 'data breach', 'data exposure']
        if any(m in content for m in critical_markers):
            severity = 'High'

        return breach_type, severity

    def _select_canonical_entity(self, article: Dict) -> Optional[Dict]:
        """
        Choose the best (company, ticker) candidate for watch creation.

        This is where we reduce false positives by selecting the candidate that is
        closest (by string distance) to a breach keyword in the article text,
        and preferring US-listed-like tickers (no '.' in symbol).
        """
        candidates = article.get("mapped_entities", []) or []
        if not candidates:
            return None

        title = article.get("title", "") or ""
        summary = article.get("summary", "") or ""
        content_lower = f"{title} {summary}".lower()
        breach_keywords = [k.lower() for k in self.news_scraper.breach_keywords]

        # Find candidate keyword positions once
        kw_positions = []
        for kw in breach_keywords:
            pos = content_lower.find(kw)
            if pos != -1:
                kw_positions.append(pos)
        # If nothing found (shouldn't happen due to earlier filtering), fall back to keyword-less
        if not kw_positions:
            kw_positions = [0]

        best = None
        # (distance, us_preference, len(company)) - smaller is better
        best_tuple = None

        for c in candidates:
            company = c.get("company", "") or ""
            ticker = (c.get("ticker", "") or "").strip()
            if not ticker or ticker == "UNKNOWN":
                continue

            company_lower = company.lower()
            comp_pos = content_lower.find(company_lower)
            if comp_pos == -1:
                # If we can't find it in text, treat as far away.
                comp_pos = 10**9

            # Distance to nearest keyword occurrence
            distance = min(abs(comp_pos - p) for p in kw_positions)
            us_preference = 1 if "." not in ticker else 0
            # Prefer shorter company strings when distance/us_preference match.
            cand_tuple = (distance, -us_preference, len(company))
            if best_tuple is None or cand_tuple < best_tuple:
                best_tuple = cand_tuple
                best = {"company": company, "ticker": ticker}

        return best

    def detect_new_breaches(self, quiet: bool = False) -> Dict:
        """
        Scan recent RSS items and create new breach watch entries.

        Uses `scraping.hours_back` only for detection; once created, watches remain active
        for `breach_watch.max_days`.
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        hours_back = int(self.settings.get('scraping', {}).get('hours_back', 24))

        if quiet:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                raw_articles = self.news_scraper.scrape_all_sources()
        else:
            raw_articles = self.news_scraper.scrape_all_sources()

        if not raw_articles:
            return {
                "articles": 0,
                "watches_created": 0,
            }

        recent_articles = self.news_scraper.filter_recent_articles(raw_articles, hours_back)
        entities = self.entity_extractor.batch_extract(recent_articles)

        times_pre_days = int(self.settings.get("price_series", {}).get("pre_days", 30))
        times_post_days = int(self.settings.get("price_series", {}).get("post_days", 30))

        created = 0

        for article in entities:
            if not article.get("has_publicly_traded"):
                continue

            canonical = self._select_canonical_entity(article)
            if not canonical:
                continue

            published = article.get("published", "Unknown")
            breach_date = self._parse_published_date(published, fallback_date=today_str)

            title = article.get("title", "") or ""
            summary = article.get("summary", "") or ""
            breach_type, severity = self._classify_breach_type_and_severity(title, summary)

            watch = {
                "ticker": canonical["ticker"],
                "company": canonical["company"],
                "breach_date": breach_date,
                "source": article.get("source", ""),
                "url": article.get("link", ""),
                "watch_start_date": breach_date,
                "last_checked_at": datetime.now().isoformat(),
                "status": "ACTIVE",
                "timeseries_saved": "No",
            }

            if self.db.add_watch_if_new(watch):
                created += 1

                # Persist breach record (for a simpler "breached public company list")
                self.db.add_breach({
                    "date_found": breach_date,
                    "company": canonical["company"],
                    "ticker": canonical["ticker"],
                    "breach_type": breach_type,
                    "severity": severity,
                    "source": watch.get("source", ""),
                    "url": watch.get("url", ""),
                    "summary": (summary or "")[:500],
                })

                # Persist price timeseries for the watch (first deliverable)
                series_rows = self.stock_analyzer.get_breach_price_series(
                    ticker=canonical["ticker"],
                    breach_date=breach_date,
                    pre_days=times_pre_days,
                    post_days=times_post_days,
                )
                if series_rows:
                    self.db.add_price_timeseries(series_rows)
                    self.db.mark_timeseries_saved(canonical["ticker"], breach_date)
            else:
                # Keep watchlist company metadata aligned with latest canonical selection.
                self.db.update_watch_metadata(
                    ticker=canonical["ticker"],
                    breach_date=breach_date,
                    company=canonical["company"],
                    source=article.get("source", ""),
                    url=article.get("link", ""),
                )

        return {
            "articles": len(recent_articles),
            "watches_created": created,
        }

    def update_watches_and_generate_signals(self, quiet: bool = False) -> Dict:
        """
        For each ACTIVE watch in the last `max_days`, analyze stock movement and create buy signals.
        """
        max_days = int(self.settings.get("breach_watch", {}).get("max_days", 7))

        active_watches = self.db.get_active_watches(max_days=max_days)
        if not active_watches:
            return {
                "watches_checked": 0,
                "signals_generated": 0,
                "signals_saved": 0,
                "new_signals": [],
            }

        # Don't spam with repeated signals
        existing_signals = self.db.get_signals()
        existing_signal_keys = {
            (s.get("ticker", ""), s.get("breach_date", ""), s.get("signal_type", ""))
            for s in existing_signals
        }

        existing_analyses = self.db.get_analysis_history()
        existing_analysis_keys = {
            (a.get("ticker", ""), a.get("breach_date", ""))
            for a in existing_analyses
        }

        analyses_requests = []
        watches_to_check = []
        for w in active_watches:
            status = (w.get("status") or "").upper()
            if status == "SIGNAL_CREATED":
                # Already signaled; still update timestamp but don't re-signal.
                self.db.mark_watch_last_checked(w.get("ticker", ""), w.get("breach_date", ""))
                continue

            ticker = w.get("ticker", "")
            breach_date = w.get("breach_date", "")
            if not ticker or not breach_date:
                continue

            watches_to_check.append(w)
            analyses_requests.append({"ticker": ticker, "company": w.get("company", ""), "breach_date": breach_date})

        if not analyses_requests:
            return {
                "watches_checked": len(watches_to_check),
                "signals_generated": 0,
                "signals_saved": 0,
                "new_signals": [],
            }

        analyses = self.stock_analyzer.batch_analyze(analyses_requests)
        signals = self.signal_generator.generate_signals_batch(analyses)
        ranked_signals = self.signal_generator.rank_signals(signals)

        min_conf = self.signal_generator.signal_config.get('min_confidence_for_signal', 0.4)
        if isinstance(min_conf, (int, float)):
            ranked_signals = self.signal_generator.filter_signals(ranked_signals, min_confidence=float(min_conf))

        saved_signals = 0
        new_signals = []

        # Save analysis metrics
        for analysis in analyses:
            a_key = (analysis.get("ticker", ""), analysis.get("breach_date", ""))
            if a_key in existing_analysis_keys or "error" in analysis:
                continue
            if self.db.add_analysis(analysis):
                existing_analysis_keys.add(a_key)

        # Save signals + mark watch
        for signal in ranked_signals:
            s_key = (signal.get("ticker", ""), signal.get("breach_date", ""), signal.get("signal_type", ""))
            if s_key in existing_signal_keys:
                continue
            if self.db.add_signal(signal):
                saved_signals += 1
                existing_signal_keys.add(s_key)
                new_signals.append(signal)
                self.db.mark_watch_signal_created(signal.get("ticker", ""), signal.get("breach_date", ""))

        # Update watch timestamps for those we checked
        for w in watches_to_check:
            self.db.mark_watch_last_checked(w.get("ticker", ""), w.get("breach_date", ""))

        # Expire watches that are now out of window
        # (Keep this lightweight; full scan is fine for CSV sizes in this MVP.)
        now = datetime.now()
        for w in active_watches:
            try:
                bd = datetime.strptime(w.get("breach_date", ""), "%Y-%m-%d")
                if (now - bd).days > max_days:
                    self.db.mark_watch_expired(w.get("ticker", ""), w.get("breach_date", ""))
            except ValueError:
                continue

        return {
            "watches_checked": len(watches_to_check),
            "signals_generated": len(signals),
            "signals_saved": saved_signals,
            "new_signals": new_signals,
        }

    def run_one_cycle(self, quiet: bool = False) -> Dict:
        """
        Run a single automatic cycle:
        1) scan for new breaches (create watch entries)
        2) update active watches and generate signals
        """
        detect_summary = self.detect_new_breaches(quiet=quiet)
        update_summary = self.update_watches_and_generate_signals(quiet=quiet)

        return {
            "articles": detect_summary.get("articles", 0),
            "watches_created": detect_summary.get("watches_created", 0),
            "watches_checked": update_summary.get("watches_checked", 0),
            "signals_generated": update_summary.get("signals_generated", 0),
            "signals_saved": update_summary.get("signals_saved", 0),
            "new_signals": update_summary.get("new_signals", []),
        }

    def scan_breaches(self) -> None:
        """Scan news sources for breaches"""
        print("\n" + "-"*80)
        print("SCANNING NEWS SOURCES")
        print("-"*80)

        # Scrape all sources
        self.current_articles = self.news_scraper.scrape_all_sources()

        if self.current_articles:
            print(f"\n✓ Found {len(self.current_articles)} breach-related articles")

            # Show preview
            print("\nSample articles:")
            for article in self.current_articles[:3]:
                print(f"  • {article.get('title', 'No title')}")
                print(f"    Source: {article.get('source')}")

            # Ask if user wants to analyze
            response = input("\nProceed to entity extraction? (y/n): ").strip().lower()
            if response == 'y':
                self.analyze_breaches()
        else:
            print("\n✗ No breach articles found in this scan")

    def analyze_breaches(self) -> None:
        """Extract entities and analyze stocks"""
        print("\n" + "-"*80)
        print("ANALYZING BREACHES")
        print("-"*80)

        if not self.current_articles:
            print("No articles to analyze. Please scan news sources first.")
            return

        print(f"\nProcessing {len(self.current_articles)} articles...")

        # Extract entities
        self.current_entities = self.entity_extractor.batch_extract(self.current_articles)
        self.entity_extractor.display_extraction_results(self.current_entities)

        # Get publicly traded companies
        publicly_traded = [e for e in self.current_entities if e.get('has_publicly_traded')]

        if publicly_traded:
            print(f"\n✓ Found {len(publicly_traded)} articles with publicly traded companies")

            # Get unique companies
            unique_companies = set()
            for entity in publicly_traded:
                for mapped in entity.get('mapped_entities', []):
                    unique_companies.add((mapped['company'], mapped['ticker']))

            print(f"✓ Unique companies to analyze: {len(unique_companies)}")

            # Ask to proceed with analysis
            response = input("\nAnalyze stock impact for these companies? (y/n): ").strip().lower()
            if response == 'y':
                # Analyze stock impact
                print("\nAnalyzing stock prices...")
                companies_to_analyze = [
                    {'company': name, 'ticker': ticker}
                    for name, ticker in unique_companies
                ]

                # Get breach date (use today for demo)
                breach_date = datetime.now().strftime('%Y-%m-%d')
                self.current_analyses = self.stock_analyzer.batch_analyze(
                    companies_to_analyze,
                    breach_date=breach_date
                )

                self.stock_analyzer.display_analysis(self.current_analyses)

                # Ask to generate signals
                response = input("\nGenerate trading signals? (y/n): ").strip().lower()
                if response == 'y':
                    self.generate_signals()
        else:
            print("\n✗ No publicly traded companies found in these articles")

    def generate_signals(self) -> None:
        """Generate trading signals from analysis"""
        print("\n" + "-"*80)
        print("GENERATING BUY SIGNALS")
        print("-"*80)

        if not self.current_analyses:
            print("No analyses available. Please analyze breaches first.")
            return

        print(f"\nGenerating signals from {len(self.current_analyses)} analyses...")

        # Generate signals
        self.current_signals = self.signal_generator.generate_signals_batch(self.current_analyses)

        if self.current_signals:
            # Rank by quality
            ranked_signals = self.signal_generator.rank_signals(self.current_signals)

            print(f"\n✓ Generated {len(ranked_signals)} buy signals")
            self.signal_generator.display_signals(ranked_signals, detailed=True)

            # Ask to save signals
            response = input("\nSave signals to database? (y/n): ").strip().lower()
            if response == 'y':
                saved = 0
                for signal in ranked_signals:
                    if self.db.add_signal(signal):
                        saved += 1

                print(f"✓ Saved {saved} signals to database")

                # Ask to save analyses too
                response = input("Save analyses to database? (y/n): ").strip().lower()
                if response == 'y':
                    saved = 0
                    for analysis in self.current_analyses:
                        if self.db.add_analysis(analysis):
                            saved += 1

                    print(f"✓ Saved {saved} analyses to database")
        else:
            print("\n✗ No trading signals generated from these analyses")
            print("   (Stock prices may not meet buy criteria)")

    def view_signals(self) -> None:
        """View trading signal history"""
        print("\n" + "-"*80)
        print("TRADING SIGNAL HISTORY")
        print("-"*80)

        signals = self.db.get_signals()

        if not signals:
            print("No signals in database yet")
            return

        # Group by confidence
        high_conf = [s for s in signals if s.get('confidence_level') == 'HIGH']
        med_conf = [s for s in signals if s.get('confidence_level') == 'MEDIUM']
        low_conf = [s for s in signals if s.get('confidence_level') == 'LOW']

        print(f"\nTotal signals: {len(signals)}")
        print(f"  HIGH confidence:   {len(high_conf)}")
        print(f"  MEDIUM confidence: {len(med_conf)}")
        print(f"  LOW confidence:    {len(low_conf)}")

        # Show recent signals
        print("\nMost recent signals:")
        print("-"*40)

        for i, signal in enumerate(signals[-10:], 1):
            status = "✓ Executed" if signal.get('executed') == 'Yes' else "⏳ Pending"
            print(f"\n{i}. {signal.get('ticker')} - {status}")
            print(f"   Confidence:  {signal.get('confidence_level')} ({signal.get('confidence_score')}/100)")
            print(f"   Entry:       ${float(signal.get('entry_price', 0)):.2f}")
            print(f"   Stop Loss:   ${float(signal.get('stop_loss', 0)):.2f}")
            print(f"   Target:      ${float(signal.get('target_price', 0)):.2f}")
            print(f"   Signal Date: {signal.get('signal_date', 'Unknown')[:10]}")

    def view_breaches(self) -> None:
        """View breach history"""
        print("\n" + "-"*80)
        print("BREACH HISTORY")
        print("-"*80)

        breaches = self.db.get_breaches()

        if not breaches:
            print("No breaches in database yet")
            return

        # Group by severity
        severity_counts = {}
        for breach in breaches:
            sev = breach.get('severity', 'Unknown')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        print(f"\nTotal breaches: {len(breaches)}")
        for sev, count in severity_counts.items():
            print(f"  {sev}: {count}")

        # Show recent breaches
        print("\nMost recent breaches:")
        print("-"*40)

        for i, breach in enumerate(breaches[-10:], 1):
            print(f"\n{i}. {breach.get('company')} ({breach.get('ticker')})")
            print(f"   Date:     {breach.get('date_found', 'Unknown')}")
            print(f"   Type:     {breach.get('breach_type', 'Unknown')}")
            print(f"   Severity: {breach.get('severity', 'Unknown')}")
            print(f"   Source:   {breach.get('source', 'Unknown')}")

    def show_statistics(self) -> None:
        """Display database statistics"""
        print("\n" + "-"*80)
        print("DATABASE STATISTICS")
        print("-"*80)

        self.db.display_statistics()

    def settings_menu(self) -> None:
        """Settings menu"""
        print("\n" + "-"*80)
        print("SETTINGS & CONFIGURATION")
        print("-"*80)
        print("\n1. View configuration")
        print("2. Export data to JSON")
        print("3. Reset database")
        print("4. Back to main menu\n")

        choice = input("Enter choice (1-4): ").strip()

        if choice == '1':
            self.view_configuration()
        elif choice == '2':
            filename = input("Enter filename (default: breach_analysis.json): ").strip()
            if not filename:
                filename = "breach_analysis.json"
            self.db.export_to_json(filename)
        elif choice == '3':
            response = input("WARNING: This will delete all data. Continue? (y/n): ").strip().lower()
            if response == 'y':
                self.reset_database()
        elif choice == '4':
            pass
        else:
            print("Invalid choice")

    def view_configuration(self) -> None:
        """View current configuration"""
        print("\n" + "="*60)
        print("Current Configuration")
        print("="*60)

        print("\nNews Sources:")
        for source, config in self.news_scraper.config.get('news_sources', {}).items():
            enabled = "✓ Enabled" if config.get('enabled') else "✗ Disabled"
            print(f"  • {source}: {enabled}")

        print("\nSignal Thresholds:")
        signals = self.signal_generator.signal_config
        print(f"  • RSI oversold threshold: {signals.get('rsi_oversold_threshold', 30)}")
        print(f"  • Price drop threshold: {signals.get('price_drop_threshold', 10)}%")
        print(f"  • Volume spike threshold: {signals.get('volume_spike_threshold', 1.5)}x")

        print("\nData Directory:")
        print(f"  • {self.db.data_dir}")

    def reset_database(self) -> None:
        """Reset all database files"""
        try:
            import os
            os.remove(self.db.breaches_file)
            os.remove(self.db.analysis_file)
            os.remove(self.db.signals_file)
            self.db._initialize_files()
            print("✓ Database reset successfully")
        except Exception as e:
            print(f"✗ Error resetting database: {e}")


def main():
    """Main entry point"""
    app = CatastropheAnalyzerApp()
    app.run()


if __name__ == '__main__':
    main()
