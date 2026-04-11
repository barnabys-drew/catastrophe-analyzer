"""
Shared service loop runtime for monitor and CLI service mode.
"""

import signal
import time
from datetime import datetime
from zoneinfo import ZoneInfo


US_MARKET_TZ = ZoneInfo("America/New_York")


def _install_signal_handlers(on_terminate):
    def handler(signum, frame):
        on_terminate()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def _is_us_market_hours(now: datetime | None = None) -> bool:
    now_et = (now or datetime.now(US_MARKET_TZ)).astimezone(US_MARKET_TZ)
    if now_et.weekday() >= 5:
        return False
    market_open = now_et.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now_et <= market_close


def _should_run_cycle(schedule_cfg: dict) -> bool:
    market_hours_only = bool(schedule_cfg.get("market_hours_only", False))
    after_hours_scan = bool(schedule_cfg.get("after_hours_scan", True))
    if not market_hours_only:
        return True
    if _is_us_market_hours():
        return True
    return after_hours_scan


def run_service_loop(app, alerts, *, quiet: bool, once: bool, interval_minutes: int | None = None) -> None:
    """
    Run production loop until terminated or single-cycle mode exits.
    """
    from runtime_cycle import run_cycle_with_alerts

    if interval_minutes is None:
        interval_minutes = int(app.settings.get("monitoring_schedule", {}).get("scan_interval_minutes", 15))
    schedule_cfg = app.settings.get("monitoring_schedule", {}) or {}

    terminated = {"value": False}

    def terminate():
        terminated["value"] = True

    _install_signal_handlers(terminate)

    while not terminated["value"]:
        if _should_run_cycle(schedule_cfg):
            run_cycle_with_alerts(app, alerts, quiet=quiet)
        if once:
            return

        # Sleep until next scan (keep SIGTERM responsive by sleeping in chunks)
        seconds = max(1, interval_minutes * 60)
        chunk = 5
        slept = 0
        while slept < seconds and not terminated["value"]:
            wait_for = min(chunk, seconds - slept)
            time.sleep(wait_for)
            slept += wait_for
