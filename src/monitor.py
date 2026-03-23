"""
Automated monitor entrypoint.

Runs the catastrophe analyzer pipeline on a schedule and sends alerts for new buy signals.
Intended for Docker: this process runs in the foreground and handles SIGTERM for clean shutdown.
"""

import argparse
import os
import signal
import sys
import time
from typing import Dict

# Ensure local imports work when executed as `python monitor.py` from this directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from main import CatastropheAnalyzerApp
from alert_manager import AlertManager


def _install_signal_handlers(on_terminate):
    def handler(signum, frame):
        on_terminate()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-minutes", type=int, default=None, help="Override scan interval")
    parser.add_argument("--quiet", action="store_true", help="Reduce console output")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    # Make relative paths inside modules predictable
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    app = CatastropheAnalyzerApp()
    alerts = AlertManager()

    interval_minutes = args.interval_minutes
    if interval_minutes is None:
        interval_minutes = int(app.settings.get("monitoring_schedule", {}).get("scan_interval_minutes", 15))

    terminated = {"value": False}

    def terminate():
        terminated["value"] = True

    _install_signal_handlers(terminate)

    # Loop until stopped
    while not terminated["value"]:
        summary: Dict = app.run_one_cycle(quiet=args.quiet)
        new_high_value_events = summary.get("new_high_value_events", []) or []
        new_signals = summary.get("new_signals", []) or []

        if new_high_value_events:
            alerts.send_high_value_event_alerts(new_high_value_events)
            app.db.mark_triage_sent([e.get("event_key", "") for e in new_high_value_events])

        if new_signals:
            alerts.send_buy_signal_alerts(new_signals)

        if args.once:
            return

        # Sleep until next scan (keep SIGTERM responsive by sleeping in chunks)
        seconds = max(1, interval_minutes * 60)
        chunk = 5
        slept = 0
        while slept < seconds and not terminated["value"]:
            time.sleep(min(chunk, seconds - slept))
            slept += chunk


if __name__ == "__main__":
    main()

