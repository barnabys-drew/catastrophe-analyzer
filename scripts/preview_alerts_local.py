#!/usr/bin/env python3
"""
Emit sample high-value + buy-signal payloads to disk (same text as ntfy), without your phone.

Uses env vars (no need to edit alerts_config.json for a quick test):

  CATASTROPHE_ALERTS_LOCAL_ONLY=1   # write data/alert_previews/*.txt and skip ntfy HTTP
  # or
  CATASTROPHE_LOCAL_ALERT_PREVIEW=1 # write files and still POST to ntfy (mirror)

Run from repo root:

  CATASTROPHE_ALERTS_LOCAL_ONLY=1 .venv/bin/python scripts/preview_alerts_local.py

Open the newest file under data/alert_previews/ or data/alert_previews/LATEST.txt.
The section "COPY-PASTE URLS" lists raw URLs extracted from the body (good for Google News links).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))
os.chdir(SRC)

from alert_manager import AlertManager  # noqa: E402


def main() -> None:
    cfg = str(REPO_ROOT / "config" / "alerts_config.json")
    alerts = AlertManager(cfg)

    alerts.send_high_value_event_alerts(
        [
            {
                "ticker": "PREVIEW",
                "company": "Preview Co",
                "event_date": "2026-03-29",
                "event_category": "cybersecurity",
                "event_subtype": "Ransomware",
                "impact_score": 80,
                "impact_likelihood": "HIGH",
                "distress_score": 65,
                "distress_likelihood": "HIGH",
                "impact_summary": "Local preview: ransomware disclosure with operational impact language.",
                "title": "Sample headline for URL block spacing",
                "url": "https://news.google.com/rss/articles/CBMiKkFVX3lxTE1J?oc=5",
            }
        ]
    )

    alerts.send_buy_signal_alerts(
        [
            {
                "ticker": "PREVIEW",
                "confidence_level": "HIGH",
                "event_date": "2026-03-29",
                "event_category": "cybersecurity",
                "event_subtype": "Ransomware",
                "issue_summary": "Local preview buy row with article URL below.",
                "title": "Buy signal sample article",
                "url": "https://www.bleepingcomputer.com/news/security/example-story/",
                "suggested_entry": 42.0,
                "suggested_stop_loss": 39.5,
                "risk_reward": {"target_price": 48.0},
                "reasons": ["RSI oversold", "Volume spike", "Drop vs pre-event"],
            }
        ]
    )

    preview_on = os.environ.get("CATASTROPHE_ALERTS_LOCAL_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.environ.get("CATASTROPHE_LOCAL_ALERT_PREVIEW", "").lower() in ("1", "true", "yes")
    if not preview_on:
        print(
            "\nTip: re-run with CATASTROPHE_ALERTS_LOCAL_ONLY=1 to write files under "
            "data/alert_previews/ and skip ntfy HTTP."
        )


if __name__ == "__main__":
    main()
