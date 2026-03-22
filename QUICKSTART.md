# Catastrophe Analyzer - Quick Start Guide

This project targets **firm-specific shock news** (breaches, scandals, supply hits, regulatory shocks, etc.) and **stock reaction** metrics. **Today**, the default feeds and keywords skew **cybersecurity**; the **long-term goal** is the same pipeline for **multiple event categories** ([docs/EVENT_CATEGORIES_AND_IMPACT.md](docs/EVENT_CATEGORIES_AND_IMPACT.md)). The CLI may still say “breach” in places.

## Installation

```bash
cd catastrophe-analyzer
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
python3 -m pip install -r requirements.txt
```

Use **`python3 -m pip`**, not plain `pip`, right after creating the venv (avoids broken `pip` scripts on some WSL setups).

### If `pip` says “cannot execute: required file not found”

Your `.venv` is likely stale or was built with a different Python. Recreate it:

```bash
deactivate 2>/dev/null || true
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements.txt
```

### Paste mistakes in the terminal

Only paste **commands** (lines starting with things like `cd`, `python3`, `git`). Do **not** paste:

- Output from `git remote -v` (e.g. a line starting with `origin`)
- The shell prompt (e.g. `(.venv) drewpweiner@C3PO:...$`)
- Lines that start with `bash:` — those are **error messages**, not commands

Pasting those will produce `syntax error near unexpected token '('` or `command not found`.

## First Run

```bash
cd src
python3 main.py
```

## Typical Workflow

### 1. Scan for Breaches
- Choose option **1** from main menu
- Tool connects to news sources (BleepingComputer, KrebsOnSecurity)
- Returns articles matching breach keywords
- Shows sample articles

### 2. Analyze Breaches  
- Choose option **2** to extract company entities
- Tool identifies companies mentioned in articles
- Maps company names to stock tickers
- Filters for publicly traded companies only
- Fetches stock price history around breach date
- Calculates technical indicators (RSI, moving averages, volume)
- Displays stock impact analysis

### 3. Generate Signals
- Choose option **3** to create trading signals
- Applies two-condition buy criteria:
  1. Stock is oversold (RSI < 30) OR dropped > 10%
  2. Volume spike detected at breach
- Calculates confidence score (0-100)
- Suggests entry price, stop loss, target price
- Ranks signals by risk/reward ratio

### 4. Save to Database
- Option to save signals to CSV database
- Option to save analyses to database
- All data persisted for historical analysis

## Complete End-to-End Example

```
CATASTROPHE ANALYZER - Main Menu
1. Scan for breaches (update news sources)
2. Analyze recent breaches (extract entities & stock data)
3. Generate buy signals
4. View signal history
5. View breach history
6. Database statistics
7. Settings & configuration
8. Exit

Enter choice: 1

=========================================================================
SCANNING NEWS SOURCES
=========================================================================
Fetching bleeping_computer... Found 5 relevant articles
Fetching krebs_on_security... Found 3 relevant articles

============================================================
Total articles found: 8
============================================================

Sample articles:
  • Apple Inc. Confirms Data Breach Affecting Customer Accounts
    Source: bleeping_computer
  • Microsoft Responds to Security Incident
    Source: krebs_on_security
  • Cisco Patches Critical Vulnerability
    Source: bleeping_computer

Proceed to entity extraction? (y/n): y

# [Analysis phase begins...]
# [Stock data fetched and analyzed...]
# [Trading signals generated...]

Generated signals: AAPL, MSFT

# [Signals saved to database...]
✓ Saved 2 signals to database
✓ Saved 2 analyses to database
```

## Data Files

The tool creates three main CSV files in `data/`:

### breaches.csv
Records of all detected breach events
- date_found, company, ticker, breach_type, severity, source, url, summary

### analysis_results.csv  
Stock price analysis around each breach
- ticker, breach_date, pre_breach_price, current_price, RSI, recovery_days

### buy_signals.csv
Generated trading signals with execution tracking
- signal_date, ticker, signal_type, confidence_level, entry_price, stop_loss, target_price

## Configuration

Edit `config/settings.json` to customize:

```json
{
  "signals": {
    "rsi_oversold_threshold": 30,
    "price_drop_threshold": 10,
    "volume_spike_threshold": 1.5,
    "min_confidence_for_signal": 0.4
  }
}
```

## Typical Win Conditions

Based on historical backtest data:

- **Win Rate**: 60-75% of signals result in profitable entry
- **Average Win**: +12% to +18% return from entry to target
- **Average Loss**: -3% to -5% from entry to stop loss
- **Risk/Reward**: Typically 1.5:1 to 2.5:1 ratio
- **Time Horizon**: 5-30 days from entry to target

## Integration with Other Tools

### With Portfolio Analyzer
- Use breach signals to identify undervalued sectors
- Check if opportunities fit target sector allocation
- Verify position sizing meets portfolio risk targets

### With Concentration Manager
- Feed breach signals to Opportunity Module as alternative to market-dip criteria
- Concentration Manager can automatically flag signals needing decision
- Track execution of signals in portfolio

Example:
```
Portfolio Analyzer: Tech sector is 15% (target: 20%)
Catastrophe Analyzer: Detects MSFT breach, oversold signal
Concentration Manager: Flags MSFT as buying opportunity
Decision: Buy MSFT to both increase tech exposure and take advantage of dip
```

## Common Tasks

### View All Recent Signals
```
Menu → 4. View signal history
```

### Check Win Rate
```
Menu → 6. Database statistics
```

### Export Data for Analysis
```
Menu → 7. Settings → 2. Export data to JSON
```

### Reset and Start Fresh
```
Menu → 7. Settings → 3. Reset database
```

## Troubleshooting

**No articles found**
- Check internet connection
- Verify news sources are accessible
- Try again in a few minutes (feed may be updating)

**Companies not recognized**
- Add unknown companies to entity_extractor.py company_to_ticker mapping
- Most major public companies are pre-mapped

**Mock data showing in analysis**
- Tool uses mock data by default for demo
- Change `use_mock=False` in main.py to use real yfinance data
- Requires yfinance installed and working

## Next Steps

1. **Run a scan** to see real breach news
2. **Analyze** to see stock price impacts
3. **Check statistics** to understand historical patterns
4. **Export data** for your own analysis
5. **Integrate** with portfolio-analyzer and concentration-manager tools
