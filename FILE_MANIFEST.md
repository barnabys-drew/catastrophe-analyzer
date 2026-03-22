# Catastrophe Analyzer - Complete File Manifest

## Project Overview

- **Name**: Catastrophe Analyzer
- **Purpose**: Cyber security breach detection and stock opportunity analysis
- **Status**: ✓ COMPLETE AND READY FOR USE
- **Location**: `catastrophe-analyzer/`
- **Python Version**: 3.8+
- **Total Code**: 2,219 lines of Python

## Directory Structure

```
catastrophe-analyzer/
├── src/                    # Main application code (6 modules + package init)
├── data/                   # CSV files created at runtime
├── config/                 # Configuration files
├── docs/                   # Reference docs (event taxonomy, impact notes)
├── README.md              # Main documentation
├── QUICKSTART.md          # Quick start guide
├── ARCHITECTURE.md        # Technical architecture
├── IMPLEMENTATION_COMPLETE.md  # Completion report
├── requirements.txt       # Python dependencies
└── (no .gitignore initially, add as needed)
```

## Python Modules (src/)

### 1. `__init__.py` (21 lines)
- Package initialization
- Exports public classes: NewsScraper, EntityExtractor, StockAnalyzer, SignalGenerator, DatabaseManager

### 2. `news_scraper.py` (285 lines)
- **Purpose**: Collect breach news from RSS feeds
- **Key Class**: `NewsScraper`
- **Key Methods**:
  - `scrape_rss_feed(feed_url, source_name)`: Fetch single feed
  - `scrape_all_sources()`: Scrape all configured feeds
  - `filter_recent_articles(articles, hours)`: Filter by recency
  - `search_by_company(articles, company_name)`: Find articles for company
  - `display_articles(articles, max_display)`: Pretty print

**Dependencies**: feedparser, requests

### 3. `entity_extractor.py` (346 lines)
- **Purpose**: Extract company names and map to tickers
- **Key Class**: `EntityExtractor`
- **Key Methods**:
  - `extract_company_mentions(text)`: Find company names in text
  - `get_ticker_for_company(company_name)`: Lookup ticker
  - `extract_and_map_companies(article)`: Process article
  - `batch_extract(articles)`: Process multiple articles
  - `get_most_mentioned_companies(articles, limit)`: Rank by mentions
- **Data**: Pre-mapped 80+ major companies to tickers

**Dependencies**: None (standard library + regex)

### 4. `stock_analyzer.py` (369 lines)
- **Purpose**: Analyze stock prices and technical indicators
- **Key Class**: `StockAnalyzer`
- **Key Methods**:
  - `get_price_history(ticker, days)`: Fetch historical data
  - `calculate_rsi(prices, period)`: Calculate RSI indicator
  - `calculate_moving_average(prices, period)`: Calculate MA
  - `calculate_volume_spike(volumes, period)`: Analyze volume
  - `analyze_breach_impact(ticker, breach_date)`: Main analysis
  - `batch_analyze(companies, breach_date)`: Multiple companies
- **Features**: Supports real yfinance data and mock data for testing

**Dependencies**: yfinance (optional, uses mock as fallback)

### 5. `signal_generator.py` (400 lines)
- **Purpose**: Generate buy signals from analysis
- **Key Class**: `SignalGenerator`
- **Key Methods**:
  - `generate_buy_signal(analysis)`: Create signal if conditions met
  - `_calculate_confidence(analysis)`: Score confidence 0-100
  - `generate_signals_batch(analyses)`: Process multiple analyses
  - `rank_signals(signals)`: Sort by attractiveness
  - `filter_signals(signals, min_confidence)`: Filter by threshold
- **Buy Criteria**: Two conditions both required:
  1. Stock oversold (RSI < 30) OR dropped > 10%
  2. Volume spike > 1.5x

**Dependencies**: json (configuration)

### 6. `database_manager.py` (446 lines)
- **Purpose**: CSV persistence and querying
- **Key Class**: `DatabaseManager`
- **CSV Files Managed**:
  - `breaches.csv`: Breach events (date, company, ticker, type, severity, source, url)
  - `analysis_results.csv`: Stock analyses (ticker, breach_date, prices, RSI, recovery)
  - `buy_signals.csv`: Trading signals (signal_date, ticker, confidence, entry, stop, target, outcome)
- **Key Methods**:
  - `add_breach(breach)`: Add breach record
  - `add_analysis(analysis)`: Add analysis result
  - `add_signal(signal)`: Add trading signal
  - `get_breaches(ticker)`: Query breaches
  - `get_signals(ticker)`: Query signals
  - `update_signal_execution(ticker, price, date)`: Mark executed
  - `get_statistics()`: Calculate stats
  - `export_to_json(filename)`: Export all data
- **Auto-initialization**: Creates CSV files with headers on first run

**Dependencies**: csv, json, os, datetime

### 7. `main.py` (352 lines)
- **Purpose**: Interactive CLI application
- **Key Class**: `CatastropheAnalyzerApp`
- **Menu Options** (1-8):
  1. Scan for breaches
  2. Analyze recent breaches
  3. Generate buy signals
  4. View signal history
  5. View breach history
  6. Database statistics
  7. Settings & configuration
  8. Exit
- **Key Methods**:
  - `run()`: Main event loop
  - `scan_breaches()`: News scanning
  - `analyze_breaches()`: Entity + stock analysis
  - `generate_signals()`: Signal creation
  - `view_signals()`: Query signal history
  - `view_breaches()`: Query breach history
  - `show_statistics()`: Database stats
  - `settings_menu()`: Configuration options

**Dependencies**: All other modules

## Configuration Files

### `config/settings.json` (70 lines)
**Purpose**: Configuration for all tool parameters

**Sections**:
- `news_sources`: RSS feed URLs and enable/disable flags
- `scraping`: Timeout, lookback window, result limits
- `entity_extraction`: Fuzzy matching settings
- `signals`: Thresholds for RSI, price drop, volume spike
- `stock_analysis`: Technical indicator periods
- `backtesting`: Simulation parameters
- `database`: CSV file location and backup settings

**Example Thresholds**:
```json
{
  "rsi_oversold_threshold": 30,
  "price_drop_threshold": 10,
  "volume_spike_threshold": 1.5,
  "min_confidence_for_signal": 0.4
}
```

## Dependencies

### `requirements.txt`
```
feedparser==6.0.10          # RSS feed parsing
beautifulsoup4==4.12.2      # HTML parsing (optional)
requests==2.31.0            # HTTP requests
yfinance==0.2.32            # Stock price data
pandas==2.1.3               # Data manipulation
nltk==3.8.1                 # NLP (optional)
textblob==0.17.1            # Text analysis (optional)
python-dateutil==2.8.2      # Date utilities
pytz==2023.3                # Timezone handling
```

**Installation**:
```bash
pip install -r requirements.txt
```

**Minimal Install** (for testing):
- Only need: feedparser, requests (yfinance optional)
- Others are for enhanced features

## Documentation Files

### `README.md` (500+ lines)
- **Sections**:
  - Purpose and use case
  - Six major features
  - Project structure
  - Installation instructions
  - Four detailed usage examples (with mock output)
  - Data file specifications
  - Integration with other tools
  - Configuration guide
  - Limitations and best practices
  - Backtesting example with realistic metrics

### `QUICKSTART.md` (200+ lines)
- **Sections**:
  - Installation steps
  - First run instructions
  - Typical workflow
  - Complete end-to-end example
  - Data files reference
  - Configuration guide
  - Integration examples
  - Common tasks
  - Troubleshooting

### `ARCHITECTURE.md` (400+ lines)
- **Sections**:
  - System overview with diagram
  - Module-by-module architecture
  - Data structures
  - Technical indicator explanations
  - Database schema
  - Integration architecture
  - Configuration system
  - Error handling
  - Performance characteristics
  - Testing strategy
  - Security considerations
  - Future enhancements

### `docs/EVENT_CATEGORIES_AND_IMPACT.md`
- **Purpose**: Canonical `event_category` ids for multi-category shock monitoring and a **full qualitative table** of news impact likelihood (High / Medium–high / …) for firm-specific headlines.
- **Contents**:
  - Rating rubric and caveats
  - Complete impact likelihood table (all shock shapes discussed for the analyzer)
  - Canonical category list: roadmap categories (`cybersecurity`, `leadership_scandal`, `supply_chain_disruption`) plus **High**-tier categories (`clinical_regulatory_binary`, `product_safety_recall`, `fraud_accounting_enforcement`, `financial_distress`, `dilutive_financing`, `ma_corporate_action`, `positive_earnings_catalyst`)
  - Optional merge notes for fewer top-level ids

### `IMPLEMENTATION_COMPLETE.md` (300+ lines)
- **Sections**:
  - Project status
  - What was built (6 modules)
  - Key features
  - Testing & validation
  - How to run
  - File structure
  - Integration points
  - Example workflow
  - Data structures
  - Performance metrics
  - Known limitations
  - Success criteria met
  - Statistics

## Data Files (Created at Runtime)

### `data/breaches.csv`
**Columns**: date_found, company, ticker, breach_type, severity, source, url, summary, date_added
**Created**: First time `DatabaseManager.add_breach()` is called
**Example Row**: 
```
2024-01-15, Apple Inc, AAPL, Data Exfiltration, High, BleepingComputer, https://..., Major breach affecting 100K users, 2024-01-17T...
```

### `data/analysis_results.csv`
**Columns**: ticker, breach_date, pre_breach_price, current_price, min_price_post_breach, max_drop_pct, recovery_days, current_rsi, volume_spike_at_breach, analysis_date
**Created**: First time `DatabaseManager.add_analysis()` is called
**Example Row**:
```
AAPL, 2024-01-15, 180.50, 160.25, 158.10, 12.2, None, 28.5, 2.1, 2024-01-17T10:30:00
```

### `data/buy_signals.csv`
**Columns**: signal_date, ticker, signal_type, confidence_level, confidence_score, entry_price, stop_loss, target_price, risk_reward_ratio, breach_date, executed, execution_price, execution_date, outcome
**Created**: First time `DatabaseManager.add_signal()` is called
**Example Row**:
```
2024-01-17T10:30:00, AAPL, BUY_OPPORTUNITY, HIGH, 82.5, 160.00, 155.20, 180.50, 2.45, 2024-01-15, No, , ,
```

## Module Dependencies Graph

```
main.py
  ├── news_scraper.py (independent)
  ├── entity_extractor.py (independent)
  ├── stock_analyzer.py (independent)
  ├── signal_generator.py (depends on config)
  └── database_manager.py (depends on csv)

news_scraper.py → feedparser, requests
entity_extractor.py → (standard library only)
stock_analyzer.py → yfinance (optional, has mock fallback)
signal_generator.py → json
database_manager.py → csv, os, json, datetime
main.py → All above modules
```

## Feature Checklist

### News Monitoring ✓
- [x] RSS feed scraping
- [x] Multiple sources (4 configured)
- [x] Keyword filtering (13 keywords)
- [x] Article deduplication
- [x] Recent article filtering

### Entity Recognition ✓
- [x] Company name extraction (regex)
- [x] Ticker mapping (80+ companies)
- [x] Publicly traded validation
- [x] Fuzzy matching capability

### Stock Analysis ✓
- [x] Historical price fetching
- [x] RSI calculation (oversold detection)
- [x] Moving average (trend analysis)
- [x] Volume spike (pressure confirmation)
- [x] Recovery time calculation
- [x] Mock data support

### Signal Generation ✓
- [x] Two-condition buy criteria
- [x] Confidence scoring (0-100)
- [x] Entry/exit price suggestions
- [x] Risk/reward calculation
- [x] Signal ranking

### Data Persistence ✓
- [x] CSV storage (3 files)
- [x] Auto-initialization
- [x] Query methods
- [x] Statistics calculation
- [x] JSON export

### User Interface ✓
- [x] Menu-driven CLI
- [x] User confirmations
- [x] Pretty printing
- [x] Error handling
- [x] Settings menu

## Installation & Usage

### Installation
```bash
cd catastrophe-analyzer
pip install -r requirements.txt
```

### Run the Application
```bash
cd src
python3 main.py
```

### Test Individual Modules
```bash
python3 news_scraper.py          # Test news scanning
python3 entity_extractor.py      # Test entity extraction
python3 stock_analyzer.py        # Test stock analysis
python3 signal_generator.py      # Test signal generation
python3 database_manager.py      # Test database operations
```

## Code Statistics

| Metric | Value |
|--------|-------|
| Total Python Lines | 2,219 |
| Total Doc Lines | ~1,400 |
| Total Config Lines | ~70 |
| Number of Modules | 6 |
| Number of Classes | 6 |
| Number of Methods | ~80 |
| Config Parameters | 50+ |
| Supported Companies | 80+ |
| News Sources | 4 |

## Testing & Validation

- ✓ All modules compile (py_compile)
- ✓ No import errors
- ✓ Sample data flows through all modules
- ✓ CSV persistence tested
- ✓ Configuration loading with defaults
- ✓ Error handling for network failures
- ✓ Menu navigation tested

## Integration Points

### With Portfolio Analyzer
- Breach signals can inform sector-level buying decisions
- Helps coordinate event-driven opportunities with allocation targets

### With Concentration Manager
- Breach signals feed into Opportunity Module
- Concentration Manager validates position sizing
- Combined signals increase decision confidence

### Shared Data
- All tools use holdings.csv (or can)
- CSV-based persistence pattern
- Compatible data models

## Getting Started

### Quick Start (5 minutes)
```bash
# 1. Install
pip install -r requirements.txt

# 2. Run
python3 src/main.py

# 3. Scan for breaches
Menu option 1

# 4. Analyze if any found
Menu option 2

# 5. Generate signals
Menu option 3

# 6. View results
Menu option 4
```

### Full Documentation
- README.md: Overview and features
- QUICKSTART.md: Step-by-step guide
- ARCHITECTURE.md: Deep technical dive
- IMPLEMENTATION_COMPLETE.md: Completion report

## File Locations Reference

- **Main App**: `catastrophe-analyzer/src/main.py`
- **Config**: `catastrophe-analyzer/config/settings.json`
- **Data**: `catastrophe-analyzer/data/`
- **Docs**: `catastrophe-analyzer/*.md`
- **Requirements**: `catastrophe-analyzer/requirements.txt`

## Next Steps

1. Install dependencies: `pip install -r requirements.txt`
2. Run the tool: `python3 src/main.py`
3. Scan for breaches
4. Analyze results
5. Generate signals
6. Check documentation for integration with other tools

---

**Status**: ✓ COMPLETE AND PRODUCTION-READY

All files created, tested, and documented. Ready for immediate use!
