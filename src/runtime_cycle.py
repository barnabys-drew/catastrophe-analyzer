"""
Shared production-cycle executor used by both CLI and monitor runtimes.
"""

import json
import logging
from typing import Dict
from runtime_health import write_runtime_heartbeat

logger = logging.getLogger(__name__)


def _confirmed_event_keys(alert_report: Dict) -> list[str]:
    """
    Return event keys with at least one successful delivery channel.
    """
    confirmed: list[str] = []
    for event_result in alert_report.get("event_results", []) or []:
        if not event_result.get("delivered"):
            continue
        key = str(event_result.get("event_key") or "").strip()
        if key:
            confirmed.append(key)
    return confirmed


def _attempted_event_keys(alert_report: Dict) -> list[str]:
    """
    Return all event keys seen in alert delivery attempts.
    """
    attempted: list[str] = []
    for event_result in alert_report.get("event_results", []) or []:
        key = str(event_result.get("event_key") or "").strip()
        if key:
            attempted.append(key)
    return attempted


def run_cycle_with_alerts(app, alerts, quiet: bool = False) -> Dict:
    """
    Execute one production cycle and dispatch alert side effects.

    This is the canonical per-cycle behavior used by service/Docker runtime.
    """
    try:
        summary: Dict = app.run_one_cycle(quiet=quiet)
    except Exception as exc:
        logger.exception("runtime_cycle_failed")
        write_runtime_heartbeat(
            repo_root=app.repo_root,
            status="error",
            summary={"runtime_metrics": {"high_value_events_detected": 0, "signals_detected": 0}},
            error=str(exc),
        )
        raise
    new_high_value_events = summary.get("new_high_value_events", []) or []
    new_signals = summary.get("new_signals", []) or []
    high_value_alert_report: Dict = {
        "kind": "high_value_events",
        "items_attempted": 0,
        "items_delivered": 0,
        "event_results": [],
        "channels": {},
    }
    signal_alert_report: Dict = {
        "kind": "buy_signals",
        "items_attempted": 0,
        "items_delivered": 0,
        "delivery_results": [],
        "channels": {},
    }

    if new_high_value_events:
        high_value_alert_report = alerts.send_high_value_event_alerts(
            new_high_value_events,
            emit_console=not quiet,
        )
        attempted_event_keys = _attempted_event_keys(high_value_alert_report)
        if attempted_event_keys:
            app.db.mark_triage_alert_attempted(attempted_event_keys)
        delivered_event_keys = _confirmed_event_keys(high_value_alert_report)
        if delivered_event_keys:
            app.db.mark_triage_sent(delivered_event_keys)

    if new_signals:
        signal_alert_report = alerts.send_buy_signal_alerts(new_signals, emit_console=not quiet)

    if not quiet:
        try:
            app.db.display_category_yield_dashboard(days=30)
        except Exception:
            pass

    runtime_metrics = {
        "high_value_events_detected": len(new_high_value_events),
        "high_value_events_delivered": int(high_value_alert_report.get("items_delivered", 0) or 0),
        "high_value_events_marked_sent": len(_confirmed_event_keys(high_value_alert_report)),
        "signals_detected": len(new_signals),
        "signal_alert_batches_delivered": int(signal_alert_report.get("items_delivered", 0) or 0),
        "alert_channels": {
            "high_value_events": high_value_alert_report.get("channels", {}),
            "buy_signals": signal_alert_report.get("channels", {}),
        },
    }
    summary["runtime_metrics"] = runtime_metrics
    logger.info("runtime_cycle_metrics=%s", json.dumps(runtime_metrics, sort_keys=True))

    write_runtime_heartbeat(
        repo_root=app.repo_root,
        status="ok",
        summary=summary,
        error="",
    )

    return summary
