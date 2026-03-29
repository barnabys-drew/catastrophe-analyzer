"""
Shared production-cycle executor used by both CLI and monitor runtimes.
"""

from typing import Dict


def run_cycle_with_alerts(app, alerts, quiet: bool = False) -> Dict:
    """
    Execute one production cycle and dispatch alert side effects.

    This is the canonical per-cycle behavior used by service/Docker runtime.
    """
    summary: Dict = app.run_one_cycle(quiet=quiet)
    new_high_value_events = summary.get("new_high_value_events", []) or []
    new_signals = summary.get("new_signals", []) or []

    if new_high_value_events:
        alerts.send_high_value_event_alerts(new_high_value_events)
        app.db.mark_triage_sent([e.get("event_key", "") for e in new_high_value_events])

    if new_signals:
        alerts.send_buy_signal_alerts(new_signals)

    return summary
