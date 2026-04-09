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

## Install Modes

Choose one of two install paths depending on your use case:

- `Repo + CLI/Dev mode` (full repo): for local development, rule tuning, tests, and interactive CLI.
- `Runtime-only Docker mode` (no full repo): for lightweight always-on service hosts.

Detailed setup guides:

- `INSTALL.md`
- `QUICKSTART.md`
- `docs/PRODUCTION_SETUP_WINDOWS_MAC_LINUX.md`
- `runtime-only/README.md`
- `docs/AGENT_AND_DEV_WORKFLOW_NOTES.md`

## WSL: run from a normal terminal (outside Cursor)

Commands in this repo assume a **Linux shell** in the **project root**. If Windows says a command is not recognized, you are usually in **PowerShell/CMD** instead of WSL, or **Docker is not available inside WSL**.

### 1) Open a WSL shell

- From Windows: Start menu → **Ubuntu** (or your distro), or run `wsl` in PowerShell.
- You should see a prompt like `username@hostname:~$` (not `C:\>`).

### 2) Go to the repo (or clone once)

```bash
cd ~/code/catastrophe-analyzer
# If the folder does not exist yet:
# git clone https://github.com/barnabys-drew/catastrophe-analyzer.git
# cd catastrophe-analyzer
```

Every `docker compose` / `python` command below must be run **after** `cd` into this directory.

### 3) Make `docker` and `docker compose` work in WSL

- Install **Docker Desktop for Windows** and start it.
- In Docker Desktop: **Settings → Resources → WSL integration** → enable your distro (e.g. Ubuntu).
- In WSL, verify:

```bash
docker version
docker compose version
```

If `docker: command not found`:

- Docker Desktop is not running, or WSL integration is off for this distro.

If `docker compose` fails but `docker` works, try the plugin form (this is what we use):

```bash
docker compose version
```

Older installs sometimes use the separate binary:

```bash
docker-compose version
```

If only `docker-compose` exists, replace `docker compose` with `docker-compose` in the commands below.

### 4) Docker: leave the service up for days

**Without Ollama (simplest):** use deterministic entity validation so the service does not depend on a local LLM. Copy the example env, then start:

```bash
cd ~/code/catastrophe-analyzer
cp profiles/agent-validation/no-ollama.env.example .env.agent
# Add TIINGO_API_TOKEN to .env.agent if you use Tiingo; otherwise yfinance is used.
docker compose --env-file .env.agent up -d --build
docker compose --env-file .env.agent ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker compose --env-file .env.agent logs -f catastrophe-analyzer
```

**With Ollama (LLM entity validation):** start Ollama on the host first, then:

```bash
cd ~/code/catastrophe-analyzer
cp profiles/agent-validation/ollama-local.env.example .env.agent
docker compose --env-file .env.agent up -d --build
docker compose --env-file .env.agent ps
docker inspect --format='{{.State.Health.Status}}' catastrophe-analyzer
docker compose --env-file .env.agent logs -f catastrophe-analyzer
```

Stop the stack later:

```bash
cd ~/code/catastrophe-analyzer
docker compose --env-file .env.agent down
```

Pause without removing containers:

```bash
docker compose --env-file .env.agent stop
```

One-off test cycle (container exits when done):

```bash
cd ~/code/catastrophe-analyzer
docker compose --env-file .env.agent run --rm catastrophe-analyzer --once --quiet
```

### 5) Python CLI in WSL (no Docker)

Cursor’s integrated terminal often auto-activates a venv; a plain WSL terminal does not.

```bash
cd ~/code/catastrophe-analyzer
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cd src
python3 monitor.py --once --quiet
```

### 6) Reports from WSL

```bash
cd ~/code/catastrophe-analyzer
source .venv/bin/activate   # if using venv
python3 scripts/generate_ticker_review_report.py --days 30
```

Output is under `review_sessions/` (gitignored except `review_sessions/README.md`).

## Current category depth

Actively wired categories:

- `cybersecurity`
- `clinical_regulatory_binary`
- `product_safety_recall`
- `fraud_accounting_enforcement`

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

Or with Compose (recommended for local 24/7 operation):

```bash
docker compose up -d --build
```

Runtime-only (no repo clone on target machine):

```bash
docker compose --env-file .env.runtime up -d
```

Use files in `runtime-only/` or export a ready-to-run bundle:

```bash
scripts/export_runtime_bundle.sh
```

Production runbook for local always-on machines:

- `docs/LOCAL_PRODUCTION_RUNBOOK.md`
- `docs/PRODUCTION_SETUP_WINDOWS_MAC_LINUX.md` (from-scratch setup on Windows/macOS/Linux)
- `runtime-only/README.md` (runtime-only deploy path)

### Market data (Tiingo EOD)

`config/settings.json` → `stock_analysis.data_source` defaults to **tiingo** for [Tiingo](https://www.tiingo.com/) end-of-day prices ([overview](https://www.tiingo.com/documentation/general/overview)).

- Set **`TIINGO_API_TOKEN`** in the environment. Local file: **`.env.tiingo`** (copy from `.env.tiingo.example`; gitignored).
- Docker Compose forwards the variable; merge env files as needed. **`docker-compose.yml` defaults `CATASTROPHE_ENTITY_VALIDATION_MODE` to `agent`** unless you override it—so for **strict rules only** (no Ollama/LLM), use e.g.  
  `docker compose --env-file profiles/agent-validation/strict-rules.env.example --env-file .env.tiingo up -d --build`  
  For Ollama/agent validation, use `--env-file .env.agent` (from `ollama-local.env.example`) instead of the strict-rules file.
- If the token is missing, the service logs a warning and **falls back to yfinance**.
- To use Yahoo only, set `"data_source": "yfinance"` under `stock_analysis` in `config/settings.json`.

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

## Entity validation mode switch

You can quickly switch ticker-validation behavior in `config/settings.json`:

- `entity_extraction.validation_mode = "agent"`: agent-first semantic validation (fail-closed recommended)
- `entity_extraction.validation_mode = "strict_rules"`: deterministic strict-rule mode only
- In `agent` mode, the extractor now runs strict category rules first, then reuses cached verdicts, and only then performs a new agent call (default max: 1 new call/article).

Temporary runtime override (no file edit):

```bash
CATASTROPHE_ENTITY_VALIDATION_MODE=strict_rules python3 src/monitor.py --once --quiet
```

For Docker/new machines and multi-model portability, you can override provider/model at runtime:

- `CATASTROPHE_ENTITY_AGENT_ENDPOINT`
- `CATASTROPHE_ENTITY_AGENT_API_KEY`
- `CATASTROPHE_ENTITY_AGENT_PROVIDER`
- `CATASTROPHE_ENTITY_AGENT_MODEL`
- `CATASTROPHE_ENTITY_VALIDATION_RUBRIC_FILE` (default `docs/ENTITY_VALIDATION_RUBRIC.md`)

Model/provider env samples (including local Ollama) are in:

- `docs/AGENT_VALIDATION_MODEL_PROFILES.md`

## Keep expanding after initial depth

The intended path is:

1. Increase precision and depth for the initial categories.
2. Add more category-specific sources and classifiers.
3. Add category-aware signal logic (including sell/exit variants).
4. Expand coverage to additional categories from the taxonomy doc.

Future category ideas are intentionally preserved in [`docs/EVENT_CATEGORIES_AND_IMPACT.md`](docs/EVENT_CATEGORIES_AND_IMPACT.md).
