"""
Shared production-cycle executor used by both CLI and monitor runtimes.
"""

from typing import Dict
from runtime_health import write_runtime_heartbeat


def run_cycle_with_alerts(app, alerts, quiet: bool = False) -> Dict:
    """
    Execute one production cycle and dispatch alert side effects.

    This is the canonical per-cycle behavior used by service/Docker runtime.
    """
    try:
        summary: Dict = app.run_one_cycle(quiet=quiet)
    except Exception as exc:
        write_runtime_heartbeat(
            repo_root=app.repo_root,
            status="error",
            summary={},
            error=str(exc),
        )
        raise
    new_high_value_events = summary.get("new_high_value_events", []) or []
    new_signals = summary.get("new_signals", []) or []

    if new_high_value_events:
        alerts.send_high_value_event_alerts(new_high_value_events)
        app.db.mark_triage_sent([e.get("event_key", "") for e in new_high_value_events])

    if new_signals:
        alerts.send_buy_signal_alerts(new_signals)

    write_runtime_heartbeat(
        repo_root=app.repo_root,
        status="ok",
        summary=summary,
        error="",
    )

    return summary
