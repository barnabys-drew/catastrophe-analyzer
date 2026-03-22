# Agent / contributor handoff

Use this file at the **start of a new session** so work stays aligned with the product direction without re-deriving context.

## What this repo is

**Catastrophe Analyzer** — monitors **firm-specific shock headlines**, links them to **tickers**, measures **post-event** price/technical behavior, and emits **rule-based signals** with optional alerts. **Cybersecurity** is the first category wired in code; the **target design** is **multiple `event_category` values** sharing one pipeline.

## Read these first (in order)

1. [README.md](README.md) — goals, current vs roadmap, **scripts vs research agents** stance.
2. [docs/EVENT_CATEGORIES_AND_IMPACT.md](docs/EVENT_CATEGORIES_AND_IMPACT.md) — canonical **`event_category`** strings and impact table.
3. [docs/IMPLEMENTATION_PLAN_MULTI_CATEGORY.md](docs/IMPLEMENTATION_PLAN_MULTI_CATEGORY.md) — **concrete Phase 1 checklist** (config, scraper, CSV migration, renames).
4. [ARCHITECTURE.md](ARCHITECTURE.md) — module responsibilities and data flow.

## Multi-agent workflow (Cursor)

- [docs/MULTI_AGENT_WORKSTREAMS.md](docs/MULTI_AGENT_WORKSTREAMS.md) — **streams A/B/C**, git branch names, merge order, file ownership.
- [docs/SESSION_PREAMBLE.md](docs/SESSION_PREAMBLE.md) — **copy-paste** text for the first message in each new Chat/Composer session.

## Naming and design rules

- Prefer **`event_category`** / **`event_categories`** in new code and config; avoid “buckets.”
- Neutral persistence: **`events.csv`**, **`event_date`**, **`event_subtype`** (see implementation plan); migrate from legacy `breach*.csv` rather than stranding users.
- Watchlist dedupe: prefer **`(ticker, event_date, event_category)`** when implementing multi-category.
- **Do not** replace the deterministic pipeline with agents-only ingestion; agents are optional **enrichers** (README).

## How to run

```bash
cd catastrophe-analyzer
pip install -r requirements.txt
cd src && python3 main.py
```

Monitor loop (alerts): `python3 monitor.py --once` or interval loop (see [src/monitor.py](src/monitor.py)). Mock prices: env `CATASTROPHE_ANALYZER_USE_MOCK_DATA=1` (legacy `BREACH_ANALYZER_USE_MOCK_DATA` may still exist).

## What is likely still outdated in code

Until Phase 1 is implemented, expect **`breach_*` names**, **`breaches.csv`**, and CLI/menu text saying “breach.” The **docs** describe the target state; **trust the implementation plan** for the next coding steps.

## Git hygiene

Do **not** commit: `.venv/`, `data/*` (runtime; keep `data/.gitkeep`), `**/__pycache__/**`. `.gitignore` is in repo root.

## Cursor rules (repo)

Project rules live under [`.cursor/rules/`](.cursor/rules/) (e.g. `catastrophe-analyzer.mdc`) and apply **always-on** reminders to read this file and the implementation plan before editing `src/` or `config/`.
