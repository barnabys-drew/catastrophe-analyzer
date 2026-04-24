# Catastrophe Analyzer

Category-driven event signal pipeline for public equities. Ingests company news, maps headlines to tickers, scores distress likelihood, and emits ranked trade signal candidates.

This is a decision-support tool, not automated execution.

## How to trade these signals

**These signals are for event-driven individual stock trades — a different strategy from the macro ETF swings in trump-macro and econ-monitor.**

The edge here is identifying company-specific distress events (recall, fraud, clinical failure, going concern) before the full price impact is reflected. The system waits for the stock to get hit, then watches for either:
- A **bounce entry** (LONG): stock is oversold, volume spike, RSI washed out — buy the panic low
- A **continuation short** (SHORT): fraud, going concern, short-seller report — expect further decline

**Step-by-step:**
1. Alert fires with ticker, entry price, stop, and target
2. Check whether it's a LONG (bounce trade) or SHORT (distress continuation)
3. For LONG — enter near the oversold low, stop below the event low, target a partial reversion
4. For SHORT — enter on a weak bounce or break of support, stop above recent high, target further decline
5. Hold for 1–10 trading days depending on category (fraud/going-concern plays develop slower than recalls)
6. Exit at target, stop, or if the narrative changes (company resolves the issue)

**Why these hold longer than macro ETF trades:**
Individual stock events develop over days to weeks. An E. coli recall hits the stock hard on day 1, but litigation risk, FDA investigations, and sales impact take time to price in. A fraud allegation may keep selling for 5–15 trading days. The system tracks T+1, T+5, T+10, and T+20 return horizons to identify where each category's edge actually lives.

**Higher risk than macro ETF trades:**
Single stocks can move 20–50% on events. Always use the stop shown in the alert. Position size smaller than you would for an ETF macro trade.

## Paper trading

Every buy signal emitted is tracked in `data/signal_outcomes.csv`. At each service cycle the system checks whether signals have enough price history to evaluate and records:
- Return at T+1, T+5, T+10, T+20 trading days
- Whether stop or target was hit during the hold window

**Self-improvement loop:**
Run the outcome summary to see which event categories and confidence levels actually predict price moves:

```python
from src.outcome_tracker import summarize_outcomes
import json

# Win rates at T+5
result = summarize_outcomes("data/signal_outcomes.csv", horizon=5)
print(json.dumps(result, indent=2))
```

Output breaks down win rate and mean return by:
- **Event category** (`product_safety_recall`, `fraud_accounting_enforcement`, etc.) — which event types have signal
- **Confidence level** (high/medium/low) — whether the scoring thresholds are calibrated

Use that data to tune distress score thresholds, per-category RSI/drop requirements, and confidence gates in `config/settings.json`.

## Active event categories

`cybersecurity` · `clinical_regulatory_binary` · `product_safety_recall` · `fraud_accounting_enforcement` · `supply_chain_disruption` · `financial_distress` · `dilutive_financing` · `ma_corporate_action` · `leadership_scandal` · `positive_earnings_catalyst`

## Pipeline

```
RSS ingestion → ticker extraction → distress scoring → price/technical analysis → signal ranking → alerts → outcome tracking
```

## Run

```bash
# Docker (recommended, always-on)
docker compose --env-file .env.agent up -d --build
docker compose --env-file .env.agent logs -f catastrophe-analyzer

# One cycle smoke test
cd src && python3 monitor.py --once --quiet

# Python CLI (dev/debug)
cd src && python3 main.py
```

Copy env profile before first run:

```bash
# No Ollama (deterministic rules only)
cp profiles/agent-validation/no-ollama.env.example .env.agent

# With Ollama (LLM entity validation)
cp profiles/agent-validation/ollama-local.env.example .env.agent
```

## Config

`config/settings.json` — categories, sources, thresholds, distress gate  
`config/alerts_config.json` — ntfy, email, Twilio credentials

Entity validation mode (no rebuild needed):

```bash
# Switch modes in settings.json
entity_extraction.validation_mode = "agent" | "strict_rules"

# Or override at runtime
CATASTROPHE_ENTITY_VALIDATION_MODE=strict_rules python3 src/monitor.py --once --quiet
```

## Market data

Defaults to Tiingo EOD (`TIINGO_API_TOKEN` in env). Falls back to yfinance if token missing.  
Override: set `stock_analysis.data_source = "yfinance"` in `config/settings.json`.

## Key files

- `src/monitor.py` — scheduled service loop
- `src/main.py` — interactive CLI
- `src/news_scraper.py` — source ingestion
- `src/entity_extractor.py` — ticker mapping and validation
- `src/stock_analyzer.py` — price/technical context
- `src/signal_generator.py` — signal logic and ranking
- `src/outcome_tracker.py` — paper trading: T+1/T+5/T+10/T+20 return tracking
- `src/database_manager.py` — CSV persistence
- `docs/EVENT_CATEGORIES_AND_IMPACT.md` — category taxonomy and expansion targets

## Env

```
ANTHROPIC_API_KEY=
TIINGO_API_TOKEN=        # optional, falls back to yfinance
```
