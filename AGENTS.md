# Contributor Handoff

## What this repo is

Catastrophe Analyzer is a category-driven event signal tool for public equities.

Goal: detect material company events, map them to tickers, evaluate likely financial pressure and technical context, then emit ranked signal candidates.

## Read order for any new session

1. `README.md`
2. `docs/EVENT_CATEGORIES_AND_IMPACT.md`
3. `ARCHITECTURE.md`
4. `docs/AGENT_AND_DEV_WORKFLOW_NOTES.md`

## Current product direction

- Production runtime is Docker + `src/monitor.py`.
- Interactive CLI (`src/main.py`) is for testing and debugging.
- Category depth is currently strongest in:
  - `cybersecurity`
  - `clinical_regulatory_binary`
  - `fraud_accounting_enforcement` (newer; tune keywords and feeds over time)
  - `supply_chain_disruption` (newer; tune keywords and feeds over time)
  - `financial_distress` (newer; tune keywords and feeds over time)
  - `dilutive_financing` (newer; tune keywords and feeds over time)
  - `ma_corporate_action` (newer; tune keywords and feeds over time)
  - `leadership_scandal` (newer; tune keywords and feeds over time)
  - `positive_earnings_catalyst` (newer; tune keywords and feeds over time)

## Core constraints

- Keep deterministic scripted ingestion as source of truth.
- Use `event_category` / `event_subtype` naming consistently.
- Preserve category expansion ideas from `docs/EVENT_CATEGORIES_AND_IMPACT.md`.
- Avoid broad refactors unless directly requested.

## Run commands

```bash
# CLI (manual test)
cd src
python3 main.py

# Service path smoke test
python3 monitor.py --once --quiet
```

## Git hygiene

Do not commit runtime artifacts:

- `.venv/`
- `data/*` (except `data/.gitkeep`)
- `**/__pycache__/**`
- `.env`
- `.env.agent` (local Docker env; often contains API tokens)
