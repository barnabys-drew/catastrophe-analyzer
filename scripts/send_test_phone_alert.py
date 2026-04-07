#!/usr/bin/env python3
"""
Send a live-style alert to your phone using the same paths as the monitor.

Uses config/alerts_config.json:
  - ntfy: install the ntfy app and subscribe to your topic (default path for “phone”).
  - sms: if provider is twilio and enabled, also sends a short SMS summary.

This is a **manual test** payload (fraud_accounting_enforcement sample), not real pipeline output.

Examples (repo root):

  .venv/bin/python scripts/send_test_phone_alert.py
  .venv/bin/python scripts/send_test_phone_alert.py --high-value-only

Dry run (no HTTP; writes data/alert_previews/ if local preview env is set):

  CATASTROPHE_ALERTS_LOCAL_ONLY=1 .venv/bin/python scripts/send_test_phone_alert.py

Override ntfy topic for a one-off test (still uses server from alerts_config.json):

  CATASTROPHE_NTFY_TOPIC=your-private-topic .venv/bin/python scripts/send_test_phone_alert.py
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"


def main() -> int:
    parser = argparse.ArgumentParser(description="Send test ntfy/SMS alerts (fraud category sample).")
    parser.add_argument(
        "--high-value-only",
        action="store_true",
        help="Only send the high-value event style alert.",
    )
    parser.add_argument(
        "--buy-only",
        action="store_true",
        help="Only send the buy-signal style alert.",
    )
    args = parser.parse_args()

    sys.path.insert(0, str(SRC_DIR))
    os.chdir(SRC_DIR)

    from alert_manager import AlertManager  # noqa: E402

    cfg_path = REPO_ROOT / "config" / "alerts_config.json"
    alerts = AlertManager(str(cfg_path))

    ntfy_cfg = (alerts.config.get("alert_channels") or {}).get("ntfy") or {}
    topic_override = (os.environ.get("CATASTROPHE_NTFY_TOPIC") or "").strip()
    if topic_override:
        alerts.config.setdefault("alert_channels", {})
        alerts.config["alert_channels"].setdefault("ntfy", dict(ntfy_cfg))
        alerts.config["alert_channels"]["ntfy"]["topic"] = topic_override

    preview_on = os.environ.get("CATASTROPHE_ALERTS_LOCAL_ONLY", "").lower() in (
        "1",
        "true",
        "yes",
    ) or os.environ.get("CATASTROPHE_LOCAL_ALERT_PREVIEW", "").lower() in ("1", "true", "yes")

    if not ntfy_cfg.get("enabled", False) and not preview_on:
        print(
            "ntfy is disabled in config/alerts_config.json and no local preview env is set.\n"
            "Enable alert_channels.ntfy.enabled, or run with:\n"
            "  CATASTROPHE_LOCAL_ALERT_PREVIEW=1   # mirror to disk + ntfy\n"
            "  CATASTROPHE_ALERTS_LOCAL_ONLY=1    # disk only, no HTTP\n",
            file=sys.stderr,
        )
        return 1

    event_day = datetime.now().strftime("%Y-%m-%d")
    article_url = "https://www.sec.gov/enforcement-litigation/litigation-releases"

    fraud_high_value = {
        "ticker": "DEMO",
        "company": "Demo Corp (TEST)",
        "event_date": event_day,
        "event_category": "fraud_accounting_enforcement",
        "event_subtype": "SEC Enforcement Action",
        "impact_score": 82,
        "impact_likelihood": "HIGH",
        "distress_score": 72,
        "distress_likelihood": "HIGH",
        "impact_summary": (
            "[TEST] Sample fraud/enforcement headline: SEC charges and civil complaint language "
            "with material weakness / internal control context — not a real signal."
        ),
        "title": "[TEST] Catastrophe Analyzer — fraud_accounting_enforcement high-value preview",
        "url": article_url,
    }

    fraud_buy = {
        "ticker": "DEMO",
        "confidence_level": "HIGH",
        "event_date": event_day,
        "event_category": "fraud_accounting_enforcement",
        "event_subtype": "Accounting Restatement",
        "issue_summary": "[TEST] Buy-row preview after enforcement-driven selloff (sample only).",
        "title": "[TEST] Catastrophe Analyzer — fraud category buy-signal preview",
        "url": article_url,
        "suggested_entry": 42.0,
        "suggested_stop_loss": 38.0,
        "risk_reward": {"target_price": 52.0, "risk_reward_ratio": 2.5},
        "reasons": ["RSI oversold (sample)", "Volume spike (sample)", "Event-linked drawdown (sample)"],
    }

    print("Sending test alerts (fraud_accounting_enforcement)…")
    if not args.buy_only:
        alerts.send_high_value_event_alerts([fraud_high_value])
    if not args.high_value_only:
        alerts.send_buy_signal_alerts([fraud_buy])

    print("Done. Check the ntfy app on your phone (and SMS if Twilio is enabled).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
