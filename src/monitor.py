"""
Automated monitor entrypoint.

Runs the catastrophe analyzer pipeline on a schedule and sends alerts for new buy signals.
Intended for Docker: this process runs in the foreground and handles SIGTERM for clean shutdown.
"""

import argparse
import os
import sys
from service_runtime import run_service_loop

# Ensure local imports work when executed as `python monitor.py` from this directory.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alert_manager import AlertManager
from main import CatastropheAnalyzerApp
from config_loader import SettingsValidationError


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--interval-minutes", type=int, default=None, help="Override scan interval")
    parser.add_argument("--quiet", action="store_true", help="Reduce console output")
    parser.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args = parser.parse_args()

    # Make relative paths inside modules predictable
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    try:
        app = CatastropheAnalyzerApp()
    except SettingsValidationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
    try:
        vmode = getattr(app.entity_extractor, "_validation_mode", "?")
    except Exception:
        vmode = "?"
    if not args.quiet:
        print(f"catastrophe-analyzer: entity validation mode={vmode}", flush=True)
    alerts = AlertManager()

    run_service_loop(
        app,
        alerts,
        quiet=args.quiet,
        once=args.once,
        interval_minutes=args.interval_minutes,
    )


if __name__ == "__main__":
    main()

