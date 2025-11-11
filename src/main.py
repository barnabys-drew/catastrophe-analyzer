"""
Breach Analyzer - Main CLI Interface
Orchestrates news scraping, entity extraction, stock analysis, and signal generation
"""

import sys
import os
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from news_scraper import NewsScraper
from entity_extractor import EntityExtractor
from stock_analyzer import StockAnalyzer
from signal_generator import SignalGenerator
from database_manager import DatabaseManager


class BreachAnalyzerApp:
    """
    Main application orchestrating all modules
    """

    def __init__(self):
        """Initialize all components"""
        self.news_scraper = NewsScraper()
        self.entity_extractor = EntityExtractor()
        self.stock_analyzer = StockAnalyzer(use_mock=True)  # Use mock data for demo
        self.signal_generator = SignalGenerator()
        self.db = DatabaseManager()

        self.current_articles = []
        self.current_entities = []
        self.current_analyses = []
        self.current_signals = []

    def display_menu(self) -> None:
        """Display main menu"""
        print("\n" + "="*80)
        print("BREACH ANALYZER - Cyber Security Event & Stock Opportunity Detection")
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
        print("BREACH ANALYZER - Starting")
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
                print("\nExiting Breach Analyzer. Goodbye!")
                break
            else:
                print("Invalid choice. Please try again.")

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
    app = BreachAnalyzerApp()
    app.run()


if __name__ == '__main__':
    main()
