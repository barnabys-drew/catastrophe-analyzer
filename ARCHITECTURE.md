# Breach Analyzer - Architecture Document

## System Overview

Breach Analyzer is an event-driven trading signal generator that:
1. Monitors cyber security news in real-time
2. Extracts publicly traded companies from breach articles
3. Analyzes stock price movements around breach events
4. Generates buy signals when specific conditions are met
5. Persists all data for historical analysis and backtesting

```
┌─────────────────┐
│  News Sources   │  (RSS Feeds from BleepingComputer, KrebsOnSecurity, etc)
└────────┬────────┘
         │
         ▼
    ┌─────────────────────┐
    │  News Scraper       │  (Extract breach articles)
    │  (news_scraper.py)  │
    └────────┬────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Entity Extractor        │  (Extract companies, map to tickers)
    │  (entity_extractor.py)   │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Stock Analyzer          │  (Fetch price data, calculate RSI, MA)
    │  (stock_analyzer.py)     │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Signal Generator        │  (Apply buy criteria, generate signals)
    │  (signal_generator.py)   │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  Database Manager        │  (Persist to CSV)
    │  (database_manager.py)   │
    └────────┬─────────────────┘
             │
             ▼
    ┌──────────────────────────┐
    │  CSV Data Files          │  (breaches, analysis, signals)
    └──────────────────────────┘
```

## Module Architecture

### 1. News Scraper (`news_scraper.py`)

**Purpose**: Collect breach-related news from multiple RSS feeds

**Key Classes**:
- `NewsScraper`: Main scraper orchestrator

**Key Methods**:
- `scrape_rss_feed(feed_url, source_name)`: Fetch and parse single feed
- `scrape_all_sources()`: Scrape all configured sources in parallel
- `filter_recent_articles(articles, hours)`: Filter by recency
- `search_by_company(articles, company_name)`: Find articles for specific company
- `display_articles(articles, max_display)`: Pretty print results

**Configuration** (from settings.json):
```json
{
  "news_sources": {
    "bleeping_computer": {
      "enabled": true,
      "url": "https://www.bleepingcomputer.com/feed/"
    }
  },
  "scraping": {
    "timeout": 10,
    "hours_back": 24
  }
}
```

**Data Flow**:
```
RSS Feed URLs → feedparser.parse() → Extract title/summary → Filter keywords → Article[]
```

**Breach Keywords** (matched case-insensitive):
- breach, data breach, security breach, hacked, cyberattack, ransomware, exploit, 
  vulnerability, compromised, attacked, security incident, data exposure, credentials leaked

**Output Data Structure**:
```python
{
    'source': str,           # e.g. 'bleeping_computer'
    'title': str,            # Article title
    'link': str,             # URL to article
    'published': str,        # Publication date
    'summary': str,          # Article text/summary
    'date_fetched': str,     # ISO format timestamp
    'content_preview': str   # First 500 chars
}
```

---

### 2. Entity Extractor (`entity_extractor.py`)

**Purpose**: Extract company names from articles and map to stock tickers

**Key Classes**:
- `EntityExtractor`: Extracts entities and maps to tickers

**Key Methods**:
- `extract_company_mentions(text)`: Find potential company names using regex patterns
- `get_ticker_for_company(company_name)`: Look up ticker symbol
- `extract_and_map_companies(article)`: Process single article
- `batch_extract(articles)`: Process multiple articles
- `get_most_mentioned_companies(articles, limit)`: Rank by frequency
- `display_extraction_results(articles)`: Pretty print results

**Company Mapping** (company_to_ticker dict):
```python
{
    'apple': 'AAPL',
    'microsoft': 'MSFT',
    'google': 'GOOGL',
    'amazon': 'AMZN',
    # ... 80+ pre-mapped companies
}
```

**Matching Strategies**:
1. **Direct match**: Exact lowercase match of company name
2. **Partial match**: Known company substring in full name
3. **Fallback**: Return None if no match found

**Output Data Structure**:
```python
{
    # ... original article data ...
    'extracted_companies': [str],     # Company names found
    'mapped_entities': [
        {
            'company': str,           # Company name
            'ticker': str,            # Stock ticker
            'confidence': str         # 'high' or 'medium'
        }
    ],
    'has_publicly_traded': bool       # Any publicly traded found
}
```

---

### 3. Stock Analyzer (`stock_analyzer.py`)

**Purpose**: Analyze stock price movements and technical indicators around breach events

**Key Classes**:
- `StockAnalyzer`: Fetches price data and calculates indicators

**Key Methods**:
- `get_price_history(ticker, days)`: Fetch historical price data
- `calculate_rsi(prices, period)`: Relative Strength Index (default period=14)
- `calculate_moving_average(prices, period)`: Simple moving average (default 20)
- `calculate_volume_spike(volumes, period)`: Volume ratio analysis
- `analyze_breach_impact(ticker, breach_date)`: Main analysis function
- `batch_analyze(companies, breach_date)`: Analyze multiple companies
- `display_analysis(results)`: Pretty print results

**Data Sources**:
- **Primary**: yfinance (real stock data)
- **Fallback**: Mock data generator (for testing without dependencies)

**Technical Indicators**:

**RSI (Relative Strength Index)**:
- Measures momentum on scale 0-100
- RSI < 30: Oversold (potential buying opportunity)
- RSI > 70: Overbought (potential selling pressure)
- Formula: RSI = 100 - (100 / (1 + RS)) where RS = avg_gain / avg_loss

**Moving Average (MA)**:
- Simple average of last N periods (default 20)
- Price below MA suggests downtrend/weakness
- Used to confirm oversold condition

**Volume Spike**:
- Ratio of current volume to average volume
- Volume spike > 1.5x suggests selling pressure
- Used to confirm breach impact

**Output Data Structure**:
```python
{
    'ticker': str,                    # Stock ticker
    'breach_date': str,               # Date of breach (YYYY-MM-DD)
    'pre_breach_price': float,        # Price before breach
    'current_price': float,           # Current price
    'min_price_post_breach': float,   # Lowest price after breach
    'max_drop_pct': float,            # Maximum drop percentage
    'recovery_days': int or None,     # Days to recover to pre-breach
    'current_rsi': float,             # Current RSI value
    'rsi_oversold': bool,             # Is RSI < 30?
    'price_below_ma20': bool,         # Is price below 20-day MA?
    'volume_spike_at_breach': float   # Volume spike ratio
}
```

---

### 4. Signal Generator (`signal_generator.py`)

**Purpose**: Generate buy signals based on breach analysis using multi-condition criteria

**Key Classes**:
- `SignalGenerator`: Generates and ranks trading signals

**Key Methods**:
- `generate_buy_signal(analysis)`: Create signal if conditions met
- `generate_signals_batch(analyses)`: Process multiple analyses
- `rank_signals(signals)`: Sort by attractiveness
- `filter_signals(signals, min_confidence)`: Filter by threshold
- `display_signals(signals, detailed)`: Pretty print results

**Buy Signal Criteria** (BOTH conditions must be met):

**Condition 1: Stock is Undersold**
- RSI < 30 (oversold), OR
- Max drop > 10% from pre-breach price

**Condition 2: Volume Confirmation**
- Volume spike > 1.5x at breach
- Confirms significant market reaction

**Confidence Score Calculation** (0-100):
```
Base Score:
  + 25 points: RSI oversold
  + 20 points: Drop > 10% (10 points if 5-10%)
  + 20 points: Volume spike > 2.0x (10 points if 1.5-2.0x)
  + 15 points: Price below 20-day moving average
  + 20 points: No recovery yet (10 points if < 3 days recovery)
  ─────────────
  = Score (capped at 100)

Confidence Level:
  - 70-100: HIGH confidence
  - 40-70: MEDIUM confidence  
  - < 40: LOW confidence
```

**Price Target Suggestions**:
```python
entry_price    = current_price (or min_price * 1.02 if recovered)
stop_loss      = min_price_post_breach * 0.97  (3% below minimum)
target_price   = pre_breach_price              (return to normal)
```

**Output Data Structure**:
```python
{
    'ticker': str,                            # Stock ticker
    'signal_type': str,                       # 'BUY_OPPORTUNITY'
    'signal_date': str,                       # ISO timestamp
    'breach_date': str,                       # Date of breach
    'price': float,                           # Current price
    'confidence': float,                      # 0-100 score
    'confidence_level': str,                  # 'HIGH', 'MEDIUM', 'LOW'
    'reasons': [str],                         # Human-readable reasons
    'suggested_entry': float,                 # Entry price
    'suggested_stop_loss': float,             # Stop loss price
    'risk_reward': {
        'entry_price': float,
        'stop_loss': float,
        'target_price': float,
        'risk_pct': float,
        'reward_pct': float,
        'risk_reward_ratio': float            # e.g. 2.5:1
    }
}
```

---

### 5. Database Manager (`database_manager.py`)

**Purpose**: Manage CSV-based persistence of all breach and signal data

**Key Classes**:
- `DatabaseManager`: CSV file manager

**Key Methods**:
- `add_breach(breach)`: Add breach record
- `add_analysis(analysis)`: Add analysis result
- `add_signal(signal)`: Add trading signal
- `get_breaches(ticker)`: Retrieve breach history
- `get_analysis_history(ticker)`: Retrieve analyses
- `get_signals(ticker, executed_only)`: Retrieve signals
- `update_signal_execution(ticker, price, date)`: Mark signal as executed
- `get_statistics()`: Calculate stats
- `export_to_json(filename)`: Export all data

**CSV File Schemas**:

**breaches.csv**:
```
date_found, company, ticker, breach_type, severity, source, url, summary, date_added
2024-01-15, Apple Inc, AAPL, Data Exfiltration, High, BleepingComputer, https://..., ...
```

**analysis_results.csv**:
```
ticker, breach_date, pre_breach_price, current_price, min_price_post_breach, max_drop_pct, recovery_days, current_rsi, volume_spike_at_breach, analysis_date
AAPL, 2024-01-15, 180.50, 160.25, 158.10, 12.2, None, 28.5, 2.1, 2024-01-17T...
```

**buy_signals.csv**:
```
signal_date, ticker, signal_type, confidence_level, confidence_score, entry_price, stop_loss, target_price, risk_reward_ratio, breach_date, executed, execution_price, execution_date, outcome
2024-01-17T10:30:00, AAPL, BUY_OPPORTUNITY, HIGH, 82.5, 160.00, 155.20, 180.50, 2.45, 2024-01-15, No, , , 
```

---

### 6. Main CLI (`main.py`)

**Purpose**: Orchestrate all modules through interactive menu

**Key Classes**:
- `BreachAnalyzerApp`: Main application controller

**Menu Options**:
1. Scan for breaches (scrape all news sources)
2. Analyze recent breaches (extract entities + analyze stocks)
3. Generate buy signals (create trading signals)
4. View signal history (query database)
5. View breach history (query database)
6. Database statistics (show aggregate stats)
7. Settings & configuration (view/export settings)
8. Exit

**Workflow**:
```
Scan News → Extract Entities → Analyze Stocks → Generate Signals → Save to DB
```

**User Interactions**:
- Menu-driven interface with clear prompts
- Confirmation steps before major operations
- Display of intermediate results
- Option to proceed to next step or abort

---

## Data Persistence Model

**File Structure**:
```
breach-analyzer/
├── data/
│   ├── breaches.csv           # Breach events
│   ├── analysis_results.csv   # Stock analyses  
│   └── buy_signals.csv        # Trading signals
├── config/
│   └── settings.json          # Configuration
└── src/
    ├── news_scraper.py
    ├── entity_extractor.py
    ├── stock_analyzer.py
    ├── signal_generator.py
    ├── database_manager.py
    ├── main.py
    └── __init__.py
```

**Data Flow**:
```
News Sources (RSS)
    ↓
Scraped Articles (in memory)
    ↓
Extracted Entities (in memory)
    ↓
Stock Analysis (in memory)
    ↓
Generated Signals (in memory)
    ↓
Save to CSV files (breaches.csv, analysis.csv, signals.csv)
```

**Querying**:
- All data persisted in CSV for permanent storage
- CSV files can be reopened later for analysis
- Statistics calculated on-demand from CSV data
- Data exportable to JSON for external analysis

---

## Integration Architecture

### With Portfolio Analyzer

**Data Exchange**:
- Breach Analyzer generates BUY_OPPORTUNITY signals for specific tickers
- Portfolio Analyzer reads signals and checks sector allocation
- If breach is in underweight sector, can recommend purchase

**Example**:
```
Tech sector: 15% (target 20%)
Breach in MSFT (tech company)
Breach Analyzer: MSFT BUY signal
Portfolio Analyzer: Confirms buying fits target allocation
Decision: BUY MSFT
```

### With Concentration Manager

**Data Exchange**:
- Breach Analyzer generates signals with confidence scores and risk/reward
- Concentration Manager's Opportunity Module can use these as decision input
- Can compare breach signals with other buying opportunities

**Example**:
```
Concentration Manager checking buying opportunities:
  1. Market dip detected (portfolio analyzer)
  2. Breach signal: CSCO oversold (breach analyzer)
  3. Governor approves buying (position < target)
  Decision: Both signals agree, strong buy recommendation
```

---

## Configuration System

**settings.json Structure**:
```json
{
  "news_sources": {
    "source_name": {
      "enabled": bool,
      "url": "string",
      "update_interval_hours": int
    }
  },
  "scraping": {
    "timeout": int,
    "hours_back": int
  },
  "signals": {
    "rsi_oversold_threshold": int,
    "price_drop_threshold": int,
    "volume_spike_threshold": float,
    "min_confidence_for_signal": float
  },
  "stock_analysis": {
    "use_mock_data": bool,
    "data_source": "yfinance"
  }
}
```

**Environment Variables** (optional):
- `BREACH_ANALYZER_DATA_DIR`: Override data directory
- `BREACH_ANALYZER_CONFIG`: Override config file location

---

## Error Handling & Resilience

**Network Errors**:
- RSS feed fetch failures caught and logged
- Tool continues with other sources if one fails
- Retry mechanism with exponential backoff

**Data Errors**:
- Invalid tickers skipped with logging
- Missing price data returns None gracefully
- CSV write errors logged but don't crash app

**Configuration Errors**:
- Missing settings.json falls back to defaults
- Invalid JSON logged and skipped
- Tool still functions with default settings

---

## Performance Characteristics

**Scraping Performance**:
- ~5 sources, ~10 relevant articles per source per run
- ~50 milliseconds per feed (includes network latency)
- Total scan time: ~500ms - 2s depending on network

**Analysis Performance**:
- ~10 articles with companies per run
- ~3 API calls per company (stock data)
- ~100ms per company analysis
- Total analysis time: ~1-2s

**Signal Generation**:
- ~5 analyses per run
- ~10ms per signal calculation
- Total signal time: ~50-100ms

**Total Runtime** (full pipeline):
- ~2-5 seconds for complete scan + analyze + signal generation

---

## Testing Strategy

**Unit Tests** (planned):
- Test RSI calculation with known values
- Test moving average calculation
- Test signal generation conditions
- Test CSV I/O operations

**Integration Tests** (planned):
- Test full pipeline with mock data
- Verify data flow through all modules
- Test database persistence and retrieval

**Manual Testing**:
- Run full app with mock data
- Verify menu navigation
- Test all data export/import paths

---

## Security Considerations

**Input Validation**:
- URLs validated before fetching
- Ticker symbols validated against known list
- JSON config validated before loading

**Data Privacy**:
- No API keys or secrets stored in repo
- All data stored locally in data/ directory
- No external data uploads

**Network Security**:
- HTTPS URLs only for feeds
- Timeout protection on HTTP requests
- No personal data collected

---

## Future Enhancements

1. **Real-time Monitoring**: Push notifications for high-confidence signals
2. **Backtesting Engine**: Simulate historical trades based on signals
3. **Machine Learning**: Improve signal quality with ML model
4. **Advanced Filtering**: Sector-specific thresholds, company size limits
5. **Risk Management**: Portfolio-level exposure limits
6. **Automated Trading**: Direct integration with brokers (E*TRADE, IB)
7. **Alert System**: Email/SMS notifications for signals
8. **Web Dashboard**: Visualization of signals and statistics
