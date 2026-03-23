# Catastrophe Analyzer

Catastrophe Analyzer is a multi-category event-to-signal pipeline for public equities.

It continuously ingests high-impact company news, maps stories to listed tickers, evaluates technical and event severity context, and produces rule-based trade signals.

## What this tool is for

- Identify company-specific shock events quickly.
- Convert headlines into structured event records by category.
- Prioritize events by likely financial impact (distress scoring).
- Generate actionable signal candidates (buy-oriented today; sell/exit logic can be expanded).
- Run continuously in Docker with alerting.

This is a decision-support tool, not automated execution.

## Current category depth

Actively wired categories:

- `cybersecurity`
- `clinical_regulatory_binary`

Event categories and future expansion targets are defined in [`docs/EVENT_CATEGORIES_AND_IMPACT.md`](docs/EVENT_CATEGORIES_AND_IMPACT.md).

## Pipeline overview

1. RSS/source ingestion by category (`news_scraper.py`)
2. Company and ticker extraction (`entity_extractor.py`)
3. Distress likelihood scoring + watch creation (`main.py`)
4. Price/technical analysis (`stock_analyzer.py`)
5. Signal generation and ranking (`signal_generator.py`)
6. Persistence (`database_manager.py`) and optional alerts (`alert_manager.py`)

## Live service model (Docker-first)

The production path is the monitor loop, not the interactive CLI.

- Monitor entrypoint: `src/monitor.py`
- Docker entrypoint: `Dockerfile` -> `python -u monitor.py`
- Alert channels: ntfy, email, Twilio (config-driven)

Run one cycle locally:

```bash
cd src
python3 monitor.py --once --quiet
```

Run continuous service in Docker:

```bash
docker build -t catastrophe-analyzer .
docker run -d --name catastrophe-analyzer \
  --restart unless-stopped \
  -v "$(pwd)/config:/app/config" \
  -v "$(pwd)/data:/app/data" \
  catastrophe-analyzer --quiet
```

## Main files

- `src/main.py` - orchestration, event classification, distress gating
- `src/monitor.py` - scheduled continuous processing loop
- `src/news_scraper.py` - source ingestion and recency filtering
- `src/entity_extractor.py` - entity/ticker mapping
- `src/stock_analyzer.py` - event-centered price analysis
- `src/signal_generator.py` - signal logic and ranking
- `src/database_manager.py` - canonical CSV persistence
- `config/settings.json` - categories, sources, thresholds, distress gate
- `config/alerts_config.json` - alert channels and credentials

## Keep expanding after initial depth

The intended path is:

1. Increase precision and depth for the initial categories.
2. Add more category-specific sources and classifiers.
3. Add category-aware signal logic (including sell/exit variants).
4. Expand coverage to additional categories from the taxonomy doc.

Future category ideas are intentionally preserved in [`docs/EVENT_CATEGORIES_AND_IMPACT.md`](docs/EVENT_CATEGORIES_AND_IMPACT.md).
