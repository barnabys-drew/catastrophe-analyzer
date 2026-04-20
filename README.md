# Catastrophe Analyzer

Category-driven event signal pipeline for public equities. Ingests company news, maps headlines to tickers, scores distress likelihood, and emits ranked trade signal candidates.

This is a decision-support tool, not automated execution.

## Active event categories

`cybersecurity` · `clinical_regulatory_binary` · `product_safety_recall` · `fraud_accounting_enforcement` · `supply_chain_disruption` · `financial_distress` · `dilutive_financing` · `ma_corporate_action` · `leadership_scandal` · `positive_earnings_catalyst`

## Pipeline

```
RSS ingestion → ticker extraction → distress scoring → price/technical analysis → signal ranking → alerts
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
- `src/database_manager.py` — CSV persistence
- `docs/EVENT_CATEGORIES_AND_IMPACT.md` — category taxonomy and expansion targets

## Env

```
ANTHROPIC_API_KEY=
TIINGO_API_TOKEN=        # optional, falls back to yfinance
```
