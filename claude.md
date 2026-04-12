# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**Homelab roadmap** (spare PC, optional local LLM, future observability): [docs/LOCAL_INFRA_ROADMAP.md](docs/LOCAL_INFRA_ROADMAP.md) — same document pattern as `concentration-manager` and `zeromouse-monitor`.

## What This Project Does

Catastrophe Analyzer is a continuous news-to-signal pipeline for public equities. It ingests RSS feeds across 10 event categories (cybersecurity breaches, FDA actions, product recalls, fraud, supply chain disruptions, financial distress, dilutive financings, M&A, leadership scandals, earnings catalysts), extracts company/ticker entities, scores event severity, and generates rule-based trade signals with entry/stop/target levels.

## Commands

**Setup:**
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Run (interactive CLI, from repo root):**
```bash
cd src && python3 main.py
```

**Run (single service cycle, for smoke testing):**
```bash
cd src && python3 monitor.py --once --quiet
```

**Run (continuous Docker service):**
```bash
docker compose up -d --build
docker logs -f catastrophe-analyzer
```

**Tests:**
```bash
# All tests
python -m unittest discover -s tests -p "test_*.py"

# Specific test class
python -m unittest tests.test_z_category_depth_regression.ClassificationRegressionTests

# Specific test method
python -m unittest tests.test_z_category_depth_regression.ClassificationRegressionTests.test_cybersecurity_subtype_material_disclosure
```

## Architecture

### Data Flow (one cycle)

```
RSS Feeds → news_scraper.py → entity_extractor.py → main.py (classify + score) → stock_analyzer.py → signal_generator.py → alert_manager.py → CSV persistence
```

1. **`news_scraper.py`** — Pulls RSS feeds configured per-category in `config/settings.json`, filters by keywords, deduplicates by URL
2. **`entity_extractor.py`** — Extracts company names, resolves tickers via Yahoo Finance; two modes: `strict_rules` (deterministic, default) or `agent` (LLM enrichment fallback)
3. **`main.py`** (`CatastropheAnalyzerApp`) — Classifies event subtype/severity via `_classify_event_subtype_and_severity()`, scores distress likelihood (0–100) via category-specific heuristics, gates watch creation at `distress_model.min_distress_for_watch`
4. **`impact_triage.py`** — Deterministic + optional LLM-assisted impact scoring; produces triage records
5. **`stock_analyzer.py`** — Computes price drop %, recovery days, RSI, MA, volume spike; uses yfinance by default or Tiingo if `TIINGO_API_TOKEN` is set
6. **`signal_generator.py`** — Rule-based signal generation (RSI < 30 + drop > 10% → entry candidate), ranks by confidence (HIGH/MEDIUM/LOW) and risk/reward ratio
7. **`alert_manager.py`** — Emits alerts to stdout, ntfy.sh, email (SMTP), or SMS (Twilio) per `config/alerts_config.json`
8. **`database_manager.py`** — Upserts all CSV files in `data/`; `runtime_health.py` writes `data/runtime_heartbeat.json`

### Entry Points

- **`src/main.py`** — Interactive CLI for manual runs, debugging, rule tuning
- **`src/monitor.py`** — Production service loop (used by Docker); runs `service_runtime.run_service_loop()` which enforces market hours and handles SIGTERM/SIGINT

### Service Loop Lifecycle (`service_runtime.py` → `runtime_cycle.py`)

The service skips cycles outside US market hours (9:30 AM–4:00 PM ET Mon–Fri) when `market_hours_only` is true. Each cycle writes a heartbeat JSON; the Docker healthcheck fails if the heartbeat is stale beyond `CATASTROPHE_HEALTH_MAX_AGE_SECONDS` (default 2400s).

### Key Configuration

- **`config/settings.json`** — Master config: event categories (keywords, RSS feeds per category, enabled flag), distress gate thresholds, signal confidence thresholds, validation mode, scan interval
- **`config/alerts_config.json`** — Alert channels: ntfy.sh topic, SMTP, Twilio
- **`profiles/agent-validation/`** — Eight `.env` profiles for LLM provider selection (strict-rules, ollama-local, OpenAI, Anthropic, Gemini, Groq, OpenRouter, xAI)

### Environment Variables

| Variable | Purpose |
|----------|---------|
| `CATASTROPHE_ENTITY_VALIDATION_MODE` | `agent` or `strict_rules` |
| `CATASTROPHE_ENTITY_AGENT_ENDPOINT/API_KEY/PROVIDER/MODEL` | LLM enrichment config |
| `TIINGO_API_TOKEN` | Optional EOD price data (falls back to yfinance) |
| `CATASTROPHE_HTTP_USER_AGENT` | Override RSS User-Agent (SEC-friendly) |
| `CATASTROPHE_LOCAL_ALERT_PREVIEW` | `1` to write local alert preview file |
| `CATASTROPHE_ANALYZER_USE_MOCK_DATA` | `1` to use mock stock data in tests |

### Runtime Data Files (`data/`)

All persistence is CSV-based; `data/.gitkeep` is the only committed file.

| File | Contents |
|------|---------|
| `events.csv` | Detected events: ticker, category, subtype, severity, distress_score |
| `watchlist.csv` | Active post-event watches (status, last_checked_at) |
| `analysis.csv` | Technical context per watch |
| `signals.csv` | Generated signals: confidence, entry/stop/target, risk/reward |
| `timeseries.csv` | Daily OHLCV snapshots around events |
| `triage.csv` | Impact triage scores |
| `runtime_heartbeat.json` | Live service state (timestamp, cycle summary) |

## Test Patterns

Tests use `unittest`. Heavy modules (news_scraper, stock_analyzer) are stubbed at import time via `types.ModuleType` stubs in `_install_main_import_stubs()` — this allows `CatastropheAnalyzerApp` classification methods to be tested in isolation without network calls or pandas overhead.

`test_z_category_depth_regression.py` must run *after* precision tests (the `z_` prefix controls discovery order).

## Development Guardrails

Per `.cursor/rules/catastrophe-analyzer.mdc` and `AGENTS.md`:
- Read `AGENTS.md` before editing `src/` or `config/`
- Any behavioral change must work through **both** `main.py` (CLI) and `monitor.py` (service); don't add CLI-only logic
- Keep `config/*.json` defaults Docker-safe (no local paths, no secrets)
- Update `requirements.txt` when adding dependencies
- Smoke test the service path after changes: `python3 monitor.py --once --quiet`
- The scripted pipeline is the system of record — LLM agents are optional enrichers only; ingestion, event records, and signal generation must remain reproducible from code/config alone
