# Breach Analyzer - Cybersecurity Incident Stock Market Tool

**Identify cyber security breaches in the news and analyze stock price movements for buying opportunities**

An automated Python tool that **runs continuously in the background**, monitoring major cybersecurity breach announcements, extracting affected company information, analyzing stock price reactions, and identifying potential "buy the dip" opportunities. **Alerts you via text message and email when new breaches are detected and buying opportunities arise.**

## Purpose

This tool answers a specific, high-value question:

**"When a major company experiences a cybersecurity breach, does its stock price drop to a level that represents a buying opportunity?"**

### Use Case
- Monitor news for significant cybersecurity incidents
- Identify publicly-traded companies affected by breaches
- Analyze stock price movements following breach announcements
- Generate buying signals when stocks appear oversold
- Track recovery patterns and historical performance
- Make data-driven decisions on breach-related equity opportunities

---

## Features

### 1. Breach News Monitoring
- Scrapes major cybersecurity news sources in real-time
- Sources:
  - BleepingComputer (industry standard for breach reporting)
  - KrebsOnSecurity (investigative reporting)
  - Dark Reading (enterprise security news)
  - TechCrunch (technology breaches)
  - General news APIs (broader coverage)

### 2. Event Extraction & Structuring
- Identifies company names from breach articles
- Extracts key details:
  - Breach date (announcement or discovery date)
  - Company name and ticker (if publicly traded)
  - Type of breach (data, ransomware, outage, etc.)
  - Severity indicators
  - Number of records/customers affected
- Validates companies are publicly traded on major exchanges
- Handles similar company names and disambiguates

### 3. Stock Price Analysis
- Fetches historical stock data around breach announcement
- Analyzes price movements:
  - Pre-breach baseline (30-day average)
  - Post-breach drop (% from baseline)
  - Time to recovery
  - 52-week context
- Calculates technical indicators:
  - RSI (oversold identification)
  - Moving averages (trend confirmation)
  - Volume analysis (capitulation indicators)

### 4. Buying Opportunity Detection
- Two-condition framework:
  1. **Stock is oversold**: Price dropped X% from 52-week high OR RSI < 30
  2. **Market context**: Overall market conditions support recovery potential
- Generates BUY signals when both conditions met
- Ranks opportunities by:
  - Depth of dip
  - Time since announcement
  - Company fundamentals
  - Market conditions

### 5. Historical Analysis & Backtesting
- Analyzes past breach events for pattern recognition
- Calculates recovery statistics:
  - Average time to recovery
  - Average return from low point
  - Success rate of buying near breach lows
- Backtests strategy on historical data
- Identifies which breach types lead to best buying opportunities

### 6. Automated Monitoring & Alerting
- ✅ **Continuous Monitoring**: Runs 24/7, scanning news sources every 5-15 minutes
- ✅ **Real-Time Breach Alerts**: Immediate notifications when new breaches are detected
- ✅ **Buy Signal Alerts**: Alerts when buying opportunities are identified
- ✅ **Email Alerts**: Detailed breach analysis sent to your email
- ✅ **SMS Alerts**: Critical breach notifications via text message
- ✅ **Alert Customization**: Configure alert thresholds and priorities
- ✅ **Daily Summary Reports**: Comprehensive daily digest of all activity

### 7. Reporting & Analysis
- Daily breach monitoring summary
- BUY/HOLD signals with reasoning
- Performance tracking:
  - How previous breach-based purchases performed
  - Win rate and average returns
  - Risk/reward profile
- Historical comparisons

---

## Project Structure

```
breach-analyzer/
├── src/
│   ├── main.py                     # Main CLI menu & workflow
│   ├── monitor.py                  # Automated monitoring daemon
│   ├── alert_manager.py            # Email/SMS alert system
│   ├── news_scraper.py             # Breach news collection
│   ├── entity_extractor.py         # Company/breach detail extraction
│   ├── stock_analyzer.py           # Price movement analysis
│   ├── signal_generator.py         # BUY signal logic
│   └── database_manager.py         # Data persistence
├── data/
│   ├── breaches.csv                # Detected breach events
│   ├── analysis_results.csv        # Analysis of each breach
│   ├── buy_signals.csv             # Generated signals & outcomes
│   └── alerts.log                  # Alert history and logs
├── config/
│   ├── settings.json               # Configuration (sources, thresholds)
│   └── alerts_config.json          # Alert channels and configuration
├── README.md                       # This file
├── ARCHITECTURE.md                 # Detailed system design
├── requirements.txt                # Python dependencies
└── QUICKSTART.md                   # Quick start guide
```

---

## How It Works

### Automated Continuous Monitoring

The platform runs continuously in the background:

```
┌─────────────────────────────────────────────────┐
│  MONITORING DAEMON (Runs 24/7)                 │
│                                                 │
│  Every 5-15 minutes:                          │
│  1. Scan news sources for breaches             │
│  2. Extract company information                │
│  3. Analyze stock price movements              │
│  4. Generate buy signals                       │
│  5. Send alerts (email/SMS) if needed          │
│                                                 │
│  Only alerts when:                             │
│  - New breach detected                         │
│  - Buying opportunity identified               │
│  - Critical market movement                    │
└─────────────────────────────────────────────────┘
```

### Workflow Steps

```
1. NEWS MONITORING (Continuous)
   └─ Scrape cybersecurity news sources every 5-15 minutes
   └─ Look for breach-related keywords
   └─ Extract articles mentioning breaches
   └─ Alert immediately when new breach detected

2. ENTITY EXTRACTION (Automatic)
   └─ Identify company names in articles
   └─ Map to stock tickers
   └─ Validate publicly traded status
   └─ Deduplicate & validate

3. STOCK ANALYSIS (Automatic)
   └─ Fetch current price
   └─ Analyze 30-day historical data
   └─ Calculate technical indicators
   └─ Identify price drops

4. SIGNAL GENERATION (Automatic)
   └─ Apply buying opportunity criteria
   └─ Generate BUY/HOLD signals
   └─ Rank by attractiveness
   └─ Send alert via email/SMS

5. TRACKING & LEARNING (Continuous)
   └─ Record all breaches in database
   └─ Track outcomes of past signals
   └─ Calculate success metrics
   └─ Refine thresholds automatically
```

### Example Analysis

```
BREACH DETECTED: SolarWinds (December 2020)
├─ Announcement Date: 2020-12-14
├─ Company: SolarWinds Corp (NYSE: SWI)
├─ Breach Type: Supply chain / software compromise
├─ Severity: Critical (US government affected)
│
├─ PRICE ANALYSIS
│  ├─ Pre-breach price (30d avg): $24.50
│  ├─ Lowest price after: $19.42
│  ├─ Max drop: -20.7%
│  ├─ Time to recovery (back to $24.50): 47 days
│  └─ 52-week context: Up 50% before breach
│
├─ TECHNICAL INDICATORS
│  ├─ RSI (day 1): 22 (oversold)
│  ├─ RSI (day 3): 28 (still oversold)
│  ├─ 50-day MA: $24.30
│  └─ Volume spike: +240% (capitulation)
│
└─ SIGNAL: BUY
   ├─ Reason: -20% drop + RSI<30 + volume spike = oversold
   ├─ Suggested entry: $20.00-$21.00
   ├─ Price target: $25.00 (recovery to baseline)
   ├─ Risk/Reward: Risk $1, Reward $4-5 = 4:1 ratio
   └─ Confidence: High (SolarWinds is mission-critical software)
```

---

## Installation & Setup

### 1. Install Dependencies

```bash
cd breach-analyzer
pip install -r requirements.txt
```

Required packages:
- `pandas` - Data manipulation
- `yfinance` - Stock price data
- `requests` - HTTP requests for news
- `beautifulsoup4` - Web scraping
- `feedparser` - RSS feed parsing
- `nltk` - Natural language processing
- `textblob` - Sentiment analysis (optional)

### 2. Configure News Sources

Edit `config/settings.json`:

```json
{
  "news_sources": {
    "bleeping_computer": {
      "enabled": true,
      "url": "https://www.bleepingcomputer.com/feed/"
    },
    "krebs_on_security": {
      "enabled": true,
      "url": "https://krebsonsecurity.com/feed/"
    },
    "dark_reading": {
      "enabled": true,
      "search_terms": ["data breach", "security incident"]
    }
  },
  "stock_analysis": {
    "min_drop_percent": 5.0,
    "rsi_threshold": 30,
    "min_volume_increase": 1.5
  }
}
```

### 3. Initialize Database

```bash
cd src
python3 main.py
# Choose: 5 (Initialize Database)
```

Creates empty CSV files for:
- `breaches.csv` - Detected breach events
- `analysis_results.csv` - Analysis data
- `buy_signals.csv` - Generated signals

### 4. Configure Alerts

Create/edit `config/alerts_config.json`:

```json
{
  "alert_channels": {
    "email": {
      "enabled": true,
      "smtp_server": "smtp.gmail.com",
      "smtp_port": 587,
      "email_from": "breach-alerts@yourdomain.com",
      "email_to": "your-email@example.com",
      "require_auth": true,
      "username": "your-email@gmail.com",
      "password": "your-app-password"
    },
    "sms": {
      "enabled": true,
      "provider": "twilio",
      "account_sid": "your-account-sid",
      "auth_token": "your-auth-token",
      "from_number": "+1234567890",
      "to_number": "+1234567890"
    }
  },
  "alert_rules": {
    "new_breach": {
      "enabled": true,
      "send_email": true,
      "send_sms": true,
      "min_severity": "high",
      "cooldown_minutes": 30
    },
    "buy_signal": {
      "enabled": true,
      "send_email": true,
      "send_sms": true,
      "min_confidence": "moderate",
      "cooldown_minutes": 60
    },
    "price_movement": {
      "enabled": true,
      "send_email": false,
      "send_sms": false,
      "threshold_percent": 10.0,
      "cooldown_minutes": 120
    },
    "daily_summary": {
      "enabled": true,
      "send_email": true,
      "send_sms": false,
      "send_time": "18:00",
      "timezone": "America/New_York"
    }
  },
  "monitoring_schedule": {
    "scan_interval_minutes": 15,
    "news_check_interval_minutes": 5,
    "market_hours_only": false,
    "after_hours_scan": true
  }
}
```

### 5. Start Automated Monitoring

**Start Continuous Monitoring:**
```bash
python3 monitor.py --daemon
# Or run as a service
python3 monitor.py --service
```

**Check Monitoring Status:**
```bash
python3 monitor.py --status
```

**Stop Monitoring:**
```bash
python3 monitor.py --stop
```

**View Alert Logs:**
```bash
tail -f data/alerts.log
```

---

## Automated Monitoring & Alert System

### Running in Monitoring Mode

The platform runs continuously in the background, scanning news sources and analyzing breaches automatically. You only receive alerts when action is needed.

**Start Monitoring:**
```bash
# Start as daemon (background process)
python3 monitor.py --daemon

# Or run as system service
python3 monitor.py --service
```

**Benefits:**
- No need to manually check for breaches
- Real-time alerts when new breaches are detected
- Immediate notifications when buying opportunities arise
- Daily summary reports of all activity

### Alert Types

#### 1. New Breach Detected Alert

Triggers immediately when a new cybersecurity breach is detected:

**Email Alert Example:**
```
Subject: 🚨 NEW BREACH DETECTED: CrowdStrike (CRWD)

BREACH ALERT - IMMEDIATE NOTIFICATION
═══════════════════════════════════════════════════

Company: CrowdStrike Holdings Inc.
Ticker: CRWD
Breach Date: November 15, 2024
Severity: CRITICAL
Type: Software Vulnerability

Details:
- Critical vulnerability discovered in endpoint protection platform
- Potential for remote code execution
- Affects versions 7.x and 8.x

Source: BleepingComputer
Article: https://www.bleepingcomputer.com/...

STOCK ANALYSIS IN PROGRESS...
Analysis will be completed within 15 minutes.
You will receive a follow-up alert with buying opportunity assessment.

View full details: http://localhost:8080/breaches/CRWD-2024-11-15
```

**SMS Alert Example:**
```
🚨 BREACH: CRWD - Critical vulnerability detected
Stock analysis in progress. Check email for details.
```

#### 2. Buy Signal Alert

Triggers when a buying opportunity is identified:

**Email Alert Example:**
```
Subject: ⚡ BUY SIGNAL: CrowdStrike (CRWD) - Breach Opportunity

BUY SIGNAL ALERT
═══════════════════════════════════════════════════

🔴 STRONG BUY RECOMMENDATION

Company: CrowdStrike Holdings Inc. (CRWD)
Breach: Software Vulnerability (Nov 15, 2024)

STOCK ANALYSIS:
─────────────────────────────────────────────────
Current Price: $28.50
Pre-Breach Price (30d avg): $32.10
Price Drop: -11.2% from baseline
52-Week High: $35.20
Drop from High: -19.0%

TECHNICAL INDICATORS:
─────────────────────────────────────────────────
RSI (14-day): 22 (VERY OVERSOLD)
50-Day MA: $31.50
Volume Increase: +240% (capitulation)
Volume Spike: YES ✓

BUYING OPPORTUNITY:
─────────────────────────────────────────────────
Entry Price: $28.50 - $29.50
Price Target: $33.00 (recovery to baseline)
Stop Loss: $26.00
Risk/Reward Ratio: 1:1.8

CONFIDENCE: HIGH
Rationale: 
- Significant oversold condition (RSI < 30)
- Volume spike indicates capitulation
- Company fundamentals remain strong
- Breach is fixable (software patch available)

RECOMMENDED ACTION:
─────────────────────────────────────────────────
Consider buying 50-100 shares at current levels.
Monitor for additional weakness before full position.

View full analysis: http://localhost:8080/signals/CRWD-2024-11-15
```

**SMS Alert Example:**
```
⚡ BUY SIGNAL: CRWD @ $28.50
Drop: -11.2%, RSI: 22 (oversold)
Target: $33.00, Risk/Reward: 1:1.8
Check email for full analysis.
```

#### 3. Daily Summary Alert

Sent daily at configured time (default: 6 PM):

**Email Alert Example:**
```
Subject: 📊 Daily Breach Analyzer Summary - November 15, 2024

DAILY SUMMARY REPORT
═══════════════════════════════════════════════════

TODAY'S ACTIVITY:
─────────────────────────────────────────────────
Breaches Detected: 3
Buy Signals Generated: 1
Companies Analyzed: 3

NEW BREACHES TODAY:
─────────────────────────────────────────────────
1. CrowdStrike (CRWD) - Critical vulnerability
   Status: BUY SIGNAL GENERATED
   
2. Okta Inc (OKTA) - Authentication bypass
   Status: Monitoring (price drop insufficient)
   
3. Private Company - Ransomware attack
   Status: Skipped (not publicly traded)

ACTIVE BUY SIGNALS:
─────────────────────────────────────────────────
1. CRWD @ $28.50 (Nov 15)
   Drop: -11.2%, Confidence: HIGH
   
2. OKTA @ $54.30 (Nov 10)
   Drop: -12.2%, Confidence: MODERATE
   Status: Still monitoring

HISTORICAL PERFORMANCE:
─────────────────────────────────────────────────
Total Signals: 47
Profitable: 32 (68%)
Average Return: +12.3%
Best Trade: +47.3% (Equifax, 2017)

View dashboard: http://localhost:8080
```

### Alert Configuration

#### Email Setup (Gmail Example)

1. **Enable App Password:**
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate app password for "Mail"

2. **Configure in alerts_config.json:**
```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "email_from": "your-email@gmail.com",
    "email_to": "your-email@gmail.com",
    "username": "your-email@gmail.com",
    "password": "your-16-char-app-password"
  }
}
```

#### SMS Setup (Twilio Example)

1. **Sign up for Twilio:**
   - Create account at twilio.com
   - Get Account SID and Auth Token
   - Purchase phone number

2. **Configure in alerts_config.json:**
```json
{
  "sms": {
    "enabled": true,
    "provider": "twilio",
    "account_sid": "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    "auth_token": "your-auth-token",
    "from_number": "+1234567890",
    "to_number": "+1234567890"
  }
}
```

### Running as a Service

**Linux (systemd):**
```bash
# Create service file
sudo nano /etc/systemd/system/breach-analyzer.service

# Enable and start
sudo systemctl enable breach-analyzer
sudo systemctl start breach-analyzer
sudo systemctl status breach-analyzer
```

**macOS (launchd):**
```bash
# Install plist file
cp config/com.breachanalyzer.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.breachanalyzer.plist
```

**Docker:**
```bash
docker run -d \
  --name breach-analyzer \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/config:/app/config \
  breach-analyzer:latest
```

### Alert Priority Levels

- **CRITICAL**: Immediate SMS + Email (e.g., major breach affecting large company)
- **HIGH**: Email + SMS (e.g., strong buy signal)
- **MEDIUM**: Email only (e.g., moderate buy signal)
- **LOW**: Daily summary only (e.g., informational updates)

### Monitoring Schedule

Default monitoring schedule:
- **News Scanning**: Every 5 minutes
- **Breach Analysis**: Every 15 minutes
- **Stock Price Updates**: Every 15 minutes (market hours)
- **Daily Summary**: 6:00 PM local time

All configurable in `alerts_config.json`.

---

## Usage Examples

### Manual Usage (On-Demand)

### Daily Breach Scan

```bash
$ python3 main.py

BREACH ANALYZER - Main Menu
1. Scan for breaches (update news)
2. Analyze recent breaches
3. Generate buy signals
4. View historical signals
5. Backtest strategy
6. Settings & configuration
7. Exit

Enter choice: 1
```

Output:
```
SCANNING NEWS SOURCES...
Fetching from BleepingComputer...
Fetching from KrebsOnSecurity...
Fetching from Dark Reading...

NEW BREACHES FOUND: 3

1. "Critical Vulnerability in Citrix Products" (Nov 2024)
   Status: Extracting details...

2. "Ransomware Attack on Dental Practice Chain" (Nov 2024)
   Status: Not publicly traded - Skipping

3. "Data Breach at Major Cloud Provider" (Nov 2024)
   Status: Analyzing stock impact...

Process Complete. Database updated.
```

### Generate Today's Signals

```bash
Enter choice: 3

SIGNAL GENERATION
Checking all known breaches for new opportunities...

═══════════════════════════════════════════════════
SIGNALS GENERATED: 2
═══════════════════════════════════════════════════

🔴 STRONG BUY: CrowdStrike Holdings (CRWD)
   Breach: Security incident (June 2024)
   Drop: -8.5% from 52-week high
   RSI: 28 (Oversold)
   Entry: $28.50-$29.00
   Target: $33.00
   Risk/Reward: 1:1.5

🟡 MODERATE BUY: Okta Inc (OKTA)
   Breach: Authentication bypass (April 2024)
   Drop: -12.2% from 52-week high
   RSI: 22 (Very oversold)
   Entry: $52.00-$54.00
   Target: $62.00
   Risk/Reward: 1:2.0
```

### View Historical Performance

```bash
Enter choice: 4

HISTORICAL SIGNAL PERFORMANCE
═══════════════════════════════════════════════════

Total Signals Generated: 47
Profitable Signals: 32 (68%)
Average Return: +12.3%
Worst Case: -4.2%
Best Case: +45.7%

Average Time to Recovery: 23 days
Average Time to Profit: 8 days

Top Performing Breach Type:
  Supply Chain Attacks: 15/20 profitable (75%)
  
Least Performing:
  Ransomware (Private Co): Often no stock impact

═══════════════════════════════════════════════════
```

### Backtest Strategy on Historical Data

```bash
Enter choice: 5

BACKTESTING ENGINE
Testing: "Buy when RSI < 30 AND price > 5% below 52-week high"
Period: 2020-2024 (4 years of breach data)

Analyzing 47 historical breach events...
[████████████████████] 100%

═══════════════════════════════════════════════════
BACKTEST RESULTS
═══════════════════════════════════════════════════

Total Signals: 47
Profitable Trades: 32 (68%)
Losing Trades: 12 (26%)
No Signal: 3 (6%)

Win Rate: 68%
Average Win: +14.2%
Average Loss: -3.5%
Profit Factor: 1.95

Maximum Drawdown: -6.2%
Best Trade: +47.3% (Equifax, Sept 2017)
Worst Trade: -8.1% (Target, Dec 2013)

Sharpe Ratio: 1.42
Risk-Adjusted Return: Moderate
═══════════════════════════════════════════════════
```

---

## Data Files

### breaches.csv
Detected cybersecurity breach events:
```
date,company,ticker,breach_type,severity,source,url
2024-11-15,CrowdStrike,CRWD,Software Flaw,Critical,BleepingComputer,https://...
2024-11-10,Okta,OKTA,Auth Bypass,High,KrebsOnSecurity,https://...
```

### analysis_results.csv
Stock analysis for each breach:
```
ticker,breach_date,pre_breach_price,lowest_price,max_drop_pct,rsi,volume_increase,recovery_days
CRWD,2024-11-15,32.10,28.50,-8.5,28,2.4,--
OKTA,2024-11-10,62.00,54.30,-12.2,22,1.8,--
```

### buy_signals.csv
Generated buy/hold signals and outcomes:
```
signal_date,ticker,signal_type,entry_price,target_price,actual_outcome,outcome_date,return_pct
2024-11-16,CRWD,BUY,28.50,33.00,PROFIT,2024-11-23,+8.7%
2024-11-11,OKTA,BUY,54.00,62.00,PENDING,--,--
```

---

## Key Concepts

### The Breach-Stock Connection

**Why do breaches create buying opportunities?**

1. **Initial Panic**: Breach announcement causes immediate stock drop
2. **Overreaction**: Market often prices in worst-case scenarios
3. **Recovery Confidence**: As details emerge, market realizes long-term impact is limited
4. **Business Continuity**: Most companies survive and recover
5. **Opportunity**: Value investors can buy oversold stocks

**Example**: When Target was hit by the 2013 breach, stock dropped 15%. It recovered fully within 3 months and was up 35% within a year.

### Signal Generation Criteria

A strong buying opportunity requires:

1. **Stock Condition**:
   - Price down 5%+ from 52-week high
   - RSI < 30 (oversold)
   - Volume spike (capitulation)

2. **Company Condition**:
   - Publicly traded (liquidity matters)
   - Market cap > $100M (avoid penny stocks)
   - Core business not threatened by breach

3. **Market Condition**:
   - Broader market not in crash mode
   - Sector performing reasonably
   - No systemic risk factors

### Breach Types & Implications

| Type | Impact | Recovery Time | Trading Opportunity |
|------|--------|---------------|--------------------|
| **Data Breach** | Moderate | 2-4 weeks | Good |
| **Ransomware** | Temporary | 1-3 weeks | Excellent |
| **Supply Chain** | Severe | 4-12 weeks | Good (longer hold) |
| **Zero-Day** | Variable | 1-2 weeks | Excellent |
| **Insider Threat** | Severe | 4-8 weeks | Good |
| **DDoS Only** | Minimal | Hours-days | Poor |

---

## Integration with Other Tools

### How Breach Analyzer Connects

```
BREACH ANALYZER (This Tool)
  │
  ├─ Detects breach events daily
  ├─ Generates buy signals
  └─ Feeds into: CONCENTRATION MANAGER
      │
      ├─ Opportunity Module could use breach signals
      ├─ Could combine with "market dip" signals
      └─ Provides additional buying criteria

PORTFOLIO ANALYZER (Strategic View)
  │
  └─ Can review breach opportunities
      ├─ Are these in underweight sectors?
      ├─ Do they fit your risk profile?
      └─ How concentrated would this exposure be?
```

**Example Integration**:
- Breach Analyzer finds CRWD dropped 8.5%
- CONCENTRATION MANAGER sees this as market dip
- PORTFOLIO ANALYZER confirms sector is underweight
- All three tools agree: This is a strong buy

---

## Limitations & Considerations

### ⚠️ Not Guaranteed
- Historical patterns may not repeat
- Market conditions change
- Breach impacts vary significantly
- No algorithm replaces human judgment

### ⚨ Data Quality Issues
- News may be delayed or incomplete
- Company identification can be ambiguous
- Not all breaches are reported
- Private companies won't have stock prices

### ⛔ Risk Factors
- Additional negative news could cause further drops
- Class action lawsuits can create new waves of selling
- Regulatory fines not always predictable
- Competitor gains from lost trust

### 📝 Best Practices
- Use as one input, not sole decision factor
- Combine with fundamental analysis
- Consider company position and management
- Don't risk capital you can't afford to lose
- Track outcomes and refine strategy

---

## Configuration

Edit `config/settings.json` to customize:

```json
{
  "news_sources": {
    "bleeping_computer": { "enabled": true },
    "krebs_on_security": { "enabled": true },
    "dark_reading": { "enabled": true }
  },
  "stock_analysis": {
    "min_drop_percent": 5.0,
    "rsi_threshold": 30,
    "min_volume_increase": 1.5,
    "min_market_cap_millions": 100
  },
  "buying_signals": {
    "confidence_threshold": "moderate",
    "max_position_size_pct": 5.0
  },
  "backtest": {
    "start_year": 2020,
    "end_year": 2024
  }
}
```

---

## Troubleshooting

### "No breaches found"
- Check internet connection
- Verify news sources are accessible
- Check `config/settings.json` - make sure sources enabled
- May need to wait for new breach news

### "Company not found in stock market"
- Ticker not in major exchanges
- Company may be private
- Name may be different in news vs financial databases
- Check stock_analyzer.py for mapping issues

### "Stock price data unavailable"
- yfinance may have service issues
- Ticker symbol may be incorrect
- Historical data may not go back far enough
- Try again later

### "Analysis seems inaccurate"
- Verify news source data quality
- Check entity extraction results
- Review stock price data alignment
- Adjust thresholds in configuration

---

## Next Steps

1. **Install** and run: `python3 main.py`
2. **Scan** for breaches: Option 1
3. **Review** generated signals: Option 3
4. **Backtest** strategy: Option 5
5. **Adjust** thresholds based on results
6. **Integrate** with other tools (Portfolio Analyzer, Concentration Manager)
7. **Monitor** and track outcomes

---

## Related Projects

- **Concentration Manager** (`../concentration-manager/`) - Can use breach signals as buying opportunities
- **Portfolio Analyzer** (`../portfolio-analyzer/`) - Can assess breach opportunity sector fit
- **Stock Manager** (`../stock-manager/`) - Original combined tool

---

**Last Updated**: November 11, 2025  
**Version**: 1.0  
**Status**: Foundation Complete, Ready for Initial Development  

This tool is designed to be practical, focused, and feed into your broader investment system.
