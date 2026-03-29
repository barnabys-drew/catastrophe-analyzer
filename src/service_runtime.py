"""
Shared service loop runtime for monitor and CLI service mode.
"""

import signal
import time


def _install_signal_handlers(on_terminate):
    def handler(signum, frame):
        on_terminate()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)


def run_service_loop(app, alerts, *, quiet: bool, once: bool, interval_minutes: int | None = None) -> None:
    """
    Run production loop until terminated or single-cycle mode exits.
    """
    from runtime_cycle import run_cycle_with_alerts

    if interval_minutes is None:
        interval_minutes = int(app.settings.get("monitoring_schedule", {}).get("scan_interval_minutes", 15))

    terminated = {"value": False}

    def terminate():
        terminated["value"] = True

    _install_signal_handlers(terminate)

    while not terminated["value"]:
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
