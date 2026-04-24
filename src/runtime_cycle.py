"""
Shared production-cycle executor used by both CLI and monitor runtimes.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict
from runtime_health import write_runtime_heartbeat
import outcome_tracker

logger = logging.getLogger(__name__)

QUALITY_SNAPSHOT_FILE = "signal_quality_weekly_snapshot.json"
DASHBOARD_READINESS_STATE_FILE = "dashboard_readiness_state.json"


def _safe_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip() or "0"))
    except (TypeError, ValueError):
        return default


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        return float(str(value).strip() or "0")
    except (TypeError, ValueError):
        return default


def _json_path(repo_root: str, filename: str) -> str:
    return os.path.join(repo_root, "data", filename)


def _load_json(path: str) -> Dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            if isinstance(payload, dict):
                return payload
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _save_json(path: str, payload: Dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _evaluate_readiness_gate(
    readiness_cfg: Dict,
    totals: Dict,
    categories_with_signals: int,
) -> Dict:
    enabled = bool(readiness_cfg.get("enabled", True))
    window_days = max(1, _safe_int(readiness_cfg.get("window_days", 7), 7))
    min_total_signals = max(0, _safe_int(readiness_cfg.get("min_total_signals", 5), 5))
    min_categories_with_signals = max(
        0,
        _safe_int(readiness_cfg.get("min_categories_with_signals", 3), 3),
    )
    min_event_to_signal_rate = max(
        0.0,
        _safe_float(readiness_cfg.get("min_event_to_signal_rate_pct", 2.0), 2.0),
    )
    min_analysis_to_signal_rate = max(
        0.0,
        _safe_float(readiness_cfg.get("min_analysis_to_signal_rate_pct", 8.0), 8.0),
    )
    checks = {
        "min_total_signals": {
            "threshold": min_total_signals,
            "actual": _safe_int(totals.get("signals", 0), 0),
        },
        "min_categories_with_signals": {
            "threshold": min_categories_with_signals,
            "actual": categories_with_signals,
        },
        "min_event_to_signal_rate_pct": {
            "threshold": min_event_to_signal_rate,
            "actual": _safe_float(totals.get("event_to_signal_rate_pct", 0.0), 0.0),
        },
        "min_analysis_to_signal_rate_pct": {
            "threshold": min_analysis_to_signal_rate,
            "actual": _safe_float(totals.get("analysis_to_signal_rate_pct", 0.0), 0.0),
        },
    }
    checks["min_total_signals"]["passed"] = checks["min_total_signals"]["actual"] >= min_total_signals
    checks["min_categories_with_signals"]["passed"] = (
        checks["min_categories_with_signals"]["actual"] >= min_categories_with_signals
    )
    checks["min_event_to_signal_rate_pct"]["passed"] = (
        checks["min_event_to_signal_rate_pct"]["actual"] >= min_event_to_signal_rate
    )
    checks["min_analysis_to_signal_rate_pct"]["passed"] = (
        checks["min_analysis_to_signal_rate_pct"]["actual"] >= min_analysis_to_signal_rate
    )
    current_window_passed = all(bool(v.get("passed")) for v in checks.values())
    return {
        "enabled": enabled,
        "window_days": window_days,
        "required_consecutive_passes": max(
            1,
            _safe_int(readiness_cfg.get("required_consecutive_passes", 2), 2),
        ),
        "checks": checks,
        "current_window_passed": current_window_passed if enabled else False,
    }


def _collect_quality_snapshot(app, summary: Dict) -> Dict:
    settings = getattr(app, "settings", {}) or {}
    readiness_cfg = settings.get("dashboard_readiness", {}) if isinstance(settings, dict) else {}
    readiness_cfg = readiness_cfg or {}
    readiness_eval = _evaluate_readiness_gate(readiness_cfg, {}, 0)
    window_days = readiness_eval.get("window_days", 7)
    dashboard = {"window_days": window_days, "as_of": datetime.now(timezone.utc).isoformat(), "rows": [], "totals": {}}
    try:
        if hasattr(app, "db") and hasattr(app.db, "get_category_yield_dashboard"):
            categories = None
            if hasattr(app, "_active_event_categories"):
                categories = app._active_event_categories()
            dashboard = app.db.get_category_yield_dashboard(days=window_days, categories=categories)
    except Exception:
        logger.exception("quality_snapshot_dashboard_failed")

    rows = dashboard.get("rows", []) or []
    totals = dashboard.get("totals", {}) or {}
    categories_with_signals = sum(1 for row in rows if _safe_int(row.get("signals", 0), 0) > 0)
    category_count = len(rows)
    coverage_pct = round((categories_with_signals / category_count) * 100.0, 1) if category_count else 0.0
    dropoff = summary.get("dropoff_breakdown", {}) or {}
    watches_considered = _safe_int(dropoff.get("watches_considered", 0), 0)
    signals_saved = _safe_int(dropoff.get("signals_saved", summary.get("signals_saved", 0)), 0)
    watch_to_saved_rate_pct = round((signals_saved / watches_considered) * 100.0, 1) if watches_considered else 0.0

    readiness_eval = _evaluate_readiness_gate(readiness_cfg, totals, categories_with_signals)
    snapshot = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "window_days": window_days,
        "quality_metrics": {
            "categories_total": category_count,
            "categories_with_signals": categories_with_signals,
            "category_signal_coverage_pct": coverage_pct,
            "watch_to_saved_rate_pct": watch_to_saved_rate_pct,
            "signals_saved_this_cycle": _safe_int(summary.get("signals_saved", 0), 0),
            "signals_after_confidence_gate_this_cycle": _safe_int(
                summary.get("signals_after_confidence_gate", 0),
                0,
            ),
            "signals_after_triage_gate_this_cycle": _safe_int(
                summary.get("signals_after_triage_gate", 0),
                0,
            ),
        },
        "dropoff_breakdown": dropoff,
        "dropoff_rates": summary.get("dropoff_rates", {}) or {},
        "gate_rejections_by_reason": summary.get("gate_rejections_by_reason", {}) or {},
        "category_gate_summary": summary.get("category_gate_summary", {}) or {},
        "yield_totals": totals,
        "yield_rows": rows,
        "dashboard_readiness": readiness_eval,
    }
    return snapshot


def _update_readiness_state(repo_root: str, readiness: Dict) -> Dict:
    state_path = _json_path(repo_root, DASHBOARD_READINESS_STATE_FILE)
    prior = _load_json(state_path)
    required_passes = max(1, _safe_int(readiness.get("required_consecutive_passes", 2), 2))
    current_passed = bool(readiness.get("current_window_passed", False))
    prior_streak = _safe_int(prior.get("consecutive_passing_windows", 0), 0)
    streak = prior_streak + 1 if current_passed else 0
    ready_now = bool(readiness.get("enabled", True)) and streak >= required_passes
    state = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "required_consecutive_passes": required_passes,
        "consecutive_passing_windows": streak,
        "current_window_passed": current_passed,
        "ready_for_dashboard_expansion": ready_now,
    }
    _save_json(state_path, state)
    return state


def _persist_quality_snapshot(repo_root: str, snapshot: Dict) -> None:
    snapshot_path = _json_path(repo_root, QUALITY_SNAPSHOT_FILE)
    history_payload = _load_json(snapshot_path)
    history = history_payload.get("history", []) if isinstance(history_payload.get("history"), list) else []
    history.append(snapshot)
    history = history[-12:]
    payload = {
        "latest": snapshot,
        "history": history,
    }
    _save_json(snapshot_path, payload)


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
    runtime_metrics["dropoff_breakdown"] = summary.get("dropoff_breakdown", {})
    runtime_metrics["dropoff_rates"] = summary.get("dropoff_rates", {})
    runtime_metrics["gate_rejections_by_reason"] = summary.get("gate_rejections_by_reason", {})
    runtime_metrics["category_gate_summary"] = summary.get("category_gate_summary", {})

    quality_snapshot = _collect_quality_snapshot(app, summary)
    readiness_state = _update_readiness_state(
        app.repo_root,
        quality_snapshot.get("dashboard_readiness", {}),
    )
    quality_snapshot["dashboard_readiness_state"] = readiness_state
    _persist_quality_snapshot(app.repo_root, quality_snapshot)
    runtime_metrics["dashboard_readiness"] = {
        **quality_snapshot.get("dashboard_readiness", {}),
        "state": readiness_state,
    }
    runtime_metrics["quality_snapshot_window_days"] = quality_snapshot.get("window_days", 7)
    runtime_metrics["categories_with_signals"] = quality_snapshot.get("quality_metrics", {}).get(
        "categories_with_signals",
        0,
    )
    runtime_metrics["category_signal_coverage_pct"] = quality_snapshot.get("quality_metrics", {}).get(
        "category_signal_coverage_pct",
        0.0,
    )
    summary["runtime_metrics"] = runtime_metrics
    summary["quality_snapshot"] = quality_snapshot
    summary["dashboard_readiness_state"] = readiness_state
    logger.info("runtime_cycle_metrics=%s", json.dumps(runtime_metrics, sort_keys=True))

    # Paper trading: compute realized returns for any signals that now have enough price history
    try:
        signals_csv = os.path.join(app.repo_root, "data", "buy_signals.csv")
        outcomes_csv = os.path.join(app.repo_root, "data", "signal_outcomes.csv")
        new_outcomes = outcome_tracker.update_outcomes_from_files(
            signals_csv=signals_csv,
            outcomes_csv=outcomes_csv,
            price_history_fn=app.stock_analyzer.get_price_history,
            history_days=45,
        )
        if new_outcomes and not quiet:
            for oc in new_outcomes:
                r5 = oc.returns_pct.get(5)
                r5_str = f"{r5:+.2f}%" if r5 is not None else "n/a"
                hit = "TARGET" if oc.hit_target else ("STOP" if oc.hit_stop else "expired")
                print(f"  [paper_trade] {oc.ticker} {oc.event_category}  T+5={r5_str}  [{hit}]")
        runtime_metrics["paper_trade_outcomes_recorded"] = len(new_outcomes)
    except Exception as _exc:
        logger.warning("outcome_tracker_error: %s", _exc)
        runtime_metrics["paper_trade_outcomes_recorded"] = 0

    write_runtime_heartbeat(
        repo_root=app.repo_root,
        status="ok",
        summary=summary,
        error="",
    )

    return summary
