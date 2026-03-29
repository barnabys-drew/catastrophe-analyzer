# Ticker review reports (generated)

Markdown reports for **manual follow-up** on each ticker: triage, article URLs, price context, and empty checklists for legitimacy / signal quality.

Generate from repo root:

```bash
.venv/bin/python scripts/generate_ticker_review_report.py --days 7
```

This writes `review_sessions/ticker-review-YYYYMMDD-HHMMSS.md`. Open that file in Cursor to work through each section.

Options:

- `--days N` — lookback window for `event_date` (default `7`)
- `--output path.md` — custom output path

Source data: `data/event_triage.csv`, `data/events.csv`, `data/analysis_results.csv`, `data/buy_signals.csv`, `data/event_watchlist.csv` (under `data/`; not committed).
