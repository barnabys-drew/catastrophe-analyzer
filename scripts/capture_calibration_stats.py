#!/usr/bin/env python3
"""
Capture and summarize calibration stats for signal reachability tuning.

Usage:
  .venv/bin/python scripts/capture_calibration_stats.py
  .venv/bin/python scripts/capture_calibration_stats.py --days 14
  .venv/bin/python scripts/capture_calibration_stats.py --no-record
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional


import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
HEARTBEAT_PATH = DATA_DIR / "runtime_heartbeat.json"
STATS_LOG_PATH = DATA_DIR / "calibration_stats.jsonl"
TRIAGE_PATH = DATA_DIR / "event_triage.csv"
SIGNALS_PATH = DATA_DIR / "buy_signals.csv"
WATCHLIST_PATH = DATA_DIR / "event_watchlist.csv"
OUTCOMES_PATH = DATA_DIR / "signal_outcomes.csv"

SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from outcome_tracker import summarize_outcomes  # type: ignore
except ImportError:  # pragma: no cover - outcome_tracker ships with repo
    summarize_outcomes = None  # type: ignore[assignment]


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _read_json(path: Path) -> Dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _parse_datetime(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def _parse_ymd(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _to_int(value: object, default: int = 0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _in_window(dt: Optional[datetime], start: datetime, end: datetime) -> bool:
    if dt is None:
        return False
    return start <= dt <= end


def _build_snapshot(days: int) -> Dict:
    now = _now_utc()
    window_start = now - timedelta(days=max(1, days))
    heartbeat = _read_json(HEARTBEAT_PATH)
    summary = heartbeat.get("summary", {}) if isinstance(heartbeat, dict) else {}

    triage_rows = _read_csv(TRIAGE_PATH)
    signal_rows = _read_csv(SIGNALS_PATH)
    watch_rows = _read_csv(WATCHLIST_PATH)

    triage_recent = 0
    triage_alerted_recent = 0
    triage_signal_reachable_recent = 0
    for row in triage_rows:
        first_seen = _parse_datetime(row.get("first_seen_at", ""))
        if _in_window(first_seen, window_start, now):
            triage_recent += 1
            impact = _to_int(row.get("impact_score", 0))
            distress = _to_int(row.get("distress_score", 0))
            if impact >= 75 and distress >= 60:
                triage_signal_reachable_recent += 1
        last_alerted = _parse_datetime(row.get("last_alerted_at", ""))
        if _in_window(last_alerted, window_start, now):
            triage_alerted_recent += 1

    signals_recent = 0
    for row in signal_rows:
        signal_dt = _parse_datetime(row.get("signal_date", "")) or _parse_ymd(row.get("event_date", ""))
        if _in_window(signal_dt, window_start, now):
            signals_recent += 1

    active_watches = sum(1 for r in watch_rows if (r.get("status", "").strip().upper() == "ACTIVE"))

    return {
        "captured_at": now.isoformat(),
        "window_days": days,
        "heartbeat_status": heartbeat.get("status", ""),
        "heartbeat_error": heartbeat.get("error", ""),
        "heartbeat_summary": {
            "articles": _to_int(summary.get("articles", 0)),
            "watches_created": _to_int(summary.get("watches_created", 0)),
            "watches_checked": _to_int(summary.get("watches_checked", 0)),
            "skipped_unapproved_validation": _to_int(summary.get("skipped_unapproved_validation", 0)),
            "skipped_untradable_candidates": _to_int(summary.get("skipped_untradable_candidates", 0)),
            "skipped_duplicate_article_ticker": _to_int(summary.get("skipped_duplicate_article_ticker", 0)),
            "signals_generated_raw": _to_int(summary.get("signals_generated_raw", 0)),
            "signals_after_confidence_gate": _to_int(summary.get("signals_after_confidence_gate", 0)),
            "signals_after_triage_gate": _to_int(summary.get("signals_after_triage_gate", 0)),
            "signals_saved": _to_int(summary.get("signals_saved", 0)),
        },
        "totals": {
            "triage_rows_total": len(triage_rows),
            "signals_rows_total": len(signal_rows),
            "watch_rows_total": len(watch_rows),
            "active_watches_total": active_watches,
        },
        "window_counts": {
            "triage_new_rows": triage_recent,
            "triage_alerted_rows": triage_alerted_recent,
            "triage_meeting_signal_bar": triage_signal_reachable_recent,
            "signals_new_rows": signals_recent,
        },
    }


def _append_snapshot(snapshot: Dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with STATS_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(snapshot) + "\n")


def _load_log() -> List[Dict]:
    if not STATS_LOG_PATH.exists():
        return []
    out: List[Dict] = []
    with STATS_LOG_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                if isinstance(item, dict):
                    out.append(item)
            except json.JSONDecodeError:
                continue
    return out


def _summarize_log(days: int, log_rows: List[Dict]) -> Dict:
    now = _now_utc()
    start = now - timedelta(days=max(1, days))
    recent: List[Dict] = []
    for row in log_rows:
        ts = _parse_datetime(str(row.get("captured_at", "")))
        if _in_window(ts, start, now):
            recent.append(row)
    if not recent:
        return {"samples": 0}

    def _avg(field: str, parent: str = "heartbeat_summary") -> float:
        values = [
            _to_int((r.get(parent, {}) or {}).get(field, 0))
            for r in recent
        ]
        if not values:
            return 0.0
        return sum(values) / len(values)

    return {
        "samples": len(recent),
        "avg_raw_per_cycle": _avg("signals_generated_raw"),
        "avg_after_confidence_per_cycle": _avg("signals_after_confidence_gate"),
        "avg_after_triage_per_cycle": _avg("signals_after_triage_gate"),
        "avg_saved_per_cycle": _avg("signals_saved"),
    }


def _pct(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return (numerator / denominator) * 100.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture and summarize calibration stats.")
    parser.add_argument("--days", type=int, default=14, help="Window for summary metrics (default: 14)")
    parser.add_argument("--no-record", action="store_true", help="Do not append a new stats snapshot")
    parser.add_argument(
        "--outcome-horizon",
        type=int,
        default=5,
        help="Horizon in trading days for signal outcome win-rate summary (default: 5)",
    )
    args = parser.parse_args()

    snapshot = _build_snapshot(days=args.days)
    if not args.no_record:
        _append_snapshot(snapshot)

    log_rows = _load_log()
    log_summary = _summarize_log(days=args.days, log_rows=log_rows)

    h = snapshot["heartbeat_summary"]
    w = snapshot["window_counts"]
    totals = snapshot["totals"]

    conf_pass = _pct(h["signals_after_confidence_gate"], h["signals_generated_raw"])
    triage_pass = _pct(h["signals_after_triage_gate"], h["signals_after_confidence_gate"])
    save_pass = _pct(h["signals_saved"], h["signals_after_triage_gate"])

    print("Calibration stats snapshot")
    print(f"- captured_at_utc: {snapshot['captured_at']}")
    print(f"- heartbeat_status: {snapshot['heartbeat_status'] or 'unknown'}")
    if snapshot["heartbeat_error"]:
        print(f"- heartbeat_error: {snapshot['heartbeat_error']}")
    print("")
    print("Latest cycle funnel:")
    print(f"- raw: {h['signals_generated_raw']}")
    print(f"- post_confidence: {h['signals_after_confidence_gate']} ({conf_pass:.1f}% of raw)")
    print(f"- post_triage: {h['signals_after_triage_gate']} ({triage_pass:.1f}% of post_confidence)")
    print(f"- saved: {h['signals_saved']} ({save_pass:.1f}% of post_triage)")
    print(f"- skipped_unapproved_validation: {h['skipped_unapproved_validation']}")
    print(f"- skipped_untradable_candidates: {h['skipped_untradable_candidates']}")
    print(f"- skipped_duplicate_article_ticker: {h['skipped_duplicate_article_ticker']}")
    print("")
    print(f"Window ({args.days}d) counts:")
    print(f"- triage_new_rows: {w['triage_new_rows']}")
    print(f"- triage_meeting_signal_bar: {w['triage_meeting_signal_bar']}")
    print(f"- triage_alerted_rows: {w['triage_alerted_rows']}")
    print(f"- signals_new_rows: {w['signals_new_rows']}")
    print("")
    print("Current totals:")
    print(f"- triage_rows_total: {totals['triage_rows_total']}")
    print(f"- signals_rows_total: {totals['signals_rows_total']}")
    print(f"- active_watches_total: {totals['active_watches_total']}")
    print("")
    print(f"Logged trend ({args.days}d):")
    print(f"- samples: {log_summary.get('samples', 0)}")
    if log_summary.get("samples", 0) > 0:
        print(f"- avg_raw_per_cycle: {log_summary['avg_raw_per_cycle']:.2f}")
        print(f"- avg_after_confidence_per_cycle: {log_summary['avg_after_confidence_per_cycle']:.2f}")
        print(f"- avg_after_triage_per_cycle: {log_summary['avg_after_triage_per_cycle']:.2f}")
        print(f"- avg_saved_per_cycle: {log_summary['avg_saved_per_cycle']:.2f}")
    print("")
    print(f"Stats log: {STATS_LOG_PATH}")

    if summarize_outcomes is not None and OUTCOMES_PATH.exists():
        try:
            outcome_summary = summarize_outcomes(str(OUTCOMES_PATH), horizon=args.outcome_horizon)
        except Exception as exc:  # pragma: no cover - diagnostic path
            outcome_summary = {"samples": 0, "error": str(exc)}
        print("")
        print(f"Signal outcomes (T+{args.outcome_horizon} close, win = return >= 0%):")
        print(f"- samples: {outcome_summary.get('samples', 0)}")
        by_cat = outcome_summary.get("by_category", {}) or {}
        if by_cat:
            print("- by_category:")
            for name, stats in sorted(by_cat.items()):
                print(
                    f"    {name}: {stats['samples']} signals, "
                    f"win_rate={stats['win_rate']*100:.1f}%, "
                    f"mean_return={stats['mean_return_pct']:.2f}%"
                )
        by_conf = outcome_summary.get("by_confidence", {}) or {}
        if by_conf:
            print("- by_confidence:")
            for name, stats in sorted(by_conf.items()):
                print(
                    f"    {name}: {stats['samples']} signals, "
                    f"win_rate={stats['win_rate']*100:.1f}%, "
                    f"mean_return={stats['mean_return_pct']:.2f}%"
                )


if __name__ == "__main__":
    main()
