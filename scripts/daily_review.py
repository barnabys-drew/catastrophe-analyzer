"""
Daily / weekly review report for catastrophe-analyzer.

Prints a human-readable summary of pipeline health, active watches,
signals, Tiingo utilization, and anything that needs attention.

Usage:
    python scripts/daily_review.py            # default 7-day lookback
    python scripts/daily_review.py --days 30
"""

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT      = Path(__file__).parent.parent
DATA_DIR  = ROOT / "data"
CONFIG    = ROOT / "config" / "settings.json"

TIINGO_FREE_DAILY_LIMIT = 1000
TIINGO_UPGRADE_THRESHOLD = 0.70   # flag when est. daily calls exceed this fraction
SCAN_INTERVAL_MINUTES_DEFAULT = 15


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _pct(n: float, d: float) -> str:
    if d <= 0:
        return "—"
    return f"{n / d * 100:.0f}%"


def _since(iso: str) -> str:
    if not iso:
        return "never"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - dt
        h = int(delta.total_seconds() // 3600)
        if h < 1:
            return f"{int(delta.total_seconds() // 60)}m ago"
        if h < 24:
            return f"{h}h ago"
        return f"{delta.days}d ago"
    except Exception:
        return iso[:16]


def _bar(pct: float, width: int = 20) -> str:
    filled = int(pct / 100 * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"]  {pct:.0f}%"


def _flag(condition: bool, msg: str) -> str:
    return f"  ⚠  {msg}" if condition else f"  ✓  {msg}"


# ── sections ─────────────────────────────────────────────────────────────────

def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title.upper()}")
    print(f"{'─' * 60}")


def print_header(hb: dict) -> None:
    ts = hb.get("timestamp", "")
    status = hb.get("status", "unknown").upper()
    error = hb.get("error", "")
    status_icon = "✓" if status == "OK" else "✗"
    print("=" * 60)
    print("  CATASTROPHE ANALYZER — REVIEW")
    print(f"  {datetime.now().strftime('%Y-%m-%d')}  |  Last cycle: {ts[11:16]} UTC  |  {status_icon} {status}")
    if error:
        print(f"  Error: {error[:80]}")
    print("=" * 60)


def print_pipeline_health(hb: dict) -> None:
    section("Pipeline Health")
    s = hb.get("summary", {})
    articles        = s.get("articles", 0)
    val_rejected    = s.get("skipped_unapproved_validation", 0)
    low_distress    = s.get("skipped_low_distress", 0)
    watches_created = s.get("watches_created", 0)

    db = s.get("dropoff_breakdown", {})
    active_watches  = db.get("active_watches_total", 0)

    val_rate = _pct(articles - val_rejected, articles) if articles else "—"

    print(f"  Articles processed (lifetime):  {articles:,}")
    print(f"  Passed validation:              {articles - val_rejected:,}  ({val_rate} pass rate)")
    print(f"  Dropped — validation:           {val_rejected:,}")
    print(f"  Dropped — low distress:         {low_distress:,}")
    print(f"  Watches created (lifetime):     {watches_created:,}")
    print(f"  Active watches now:             {active_watches}")

    # gate rejections
    gate = s.get("gate_rejections_by_reason", {})
    if gate:
        print(f"\n  Last-cycle gate rejections:")
        for reason, count in sorted(gate.items(), key=lambda x: -x[1]):
            print(f"    {reason:<35} {count}")


def print_tiingo_utilization(hb: dict) -> None:
    section("Tiingo API Utilization")
    cfg = _load_json(CONFIG)
    stock_cfg = cfg.get("stock_analysis", {})
    interval_min = cfg.get("monitoring_schedule", {}).get("scan_interval_minutes", SCAN_INTERVAL_MINUTES_DEFAULT)
    tiingo_limit = int(stock_cfg.get("tiingo_rate_limit_per_hour", 45))

    db = hb.get("summary", {}).get("dropoff_breakdown", {})
    active_watches = db.get("active_watches_total", 0)

    cycles_per_day = int(1440 / max(1, interval_min))
    est_daily_calls = active_watches * cycles_per_day
    utilization_pct = est_daily_calls / TIINGO_FREE_DAILY_LIMIT * 100
    upgrade_watch_count = int(TIINGO_FREE_DAILY_LIMIT * TIINGO_UPGRADE_THRESHOLD / cycles_per_day)

    print(f"  Scan interval:          {interval_min} min  →  ~{cycles_per_day} cycles/day")
    print(f"  Active watches:         {active_watches}")
    print(f"  Est. daily Tiingo calls:{est_daily_calls:>6}  /  {TIINGO_FREE_DAILY_LIMIT} free tier")
    print(f"  Utilization:            {_bar(utilization_pct)}")
    print()
    if utilization_pct >= TIINGO_UPGRADE_THRESHOLD * 100:
        print(f"  ⚠  UPGRADE RECOMMENDED — exceeds {int(TIINGO_UPGRADE_THRESHOLD*100)}% of free tier")
    else:
        headroom = TIINGO_FREE_DAILY_LIMIT * TIINGO_UPGRADE_THRESHOLD - est_daily_calls
        watches_until_upgrade = max(0, upgrade_watch_count - active_watches)
        print(f"  ✓  OK — headroom for ~{watches_until_upgrade} more watches before upgrade needed")


def print_active_watches(watchlist: list[dict]) -> None:
    section("Active Watches")
    active = [w for w in watchlist if w.get("status", "").upper() == "ACTIVE"]
    if not active:
        print("  None.")
        return
    for w in sorted(active, key=lambda x: x.get("watch_start_date", "")):
        ticker   = w.get("ticker", "?")
        category = w.get("event_category", "")
        subtype  = w.get("event_subtype", "")
        edate    = w.get("event_date", "")
        checked  = _since(w.get("last_checked_at", ""))
        distress = w.get("distress_score", "")
        cat_str  = f"{category}" + (f" / {subtype}" if subtype else "")
        print(f"  {ticker:<8} {cat_str:<35} event: {edate}  checked: {checked}  distress: {distress}")

    expired = [w for w in watchlist if w.get("status", "").upper() == "EXPIRED"]
    if expired:
        print(f"\n  Expired: {len(expired)}")


def print_high_value_events(triage: list[dict], days: int) -> None:
    section(f"High-Value Events (last {days} days)")
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    recent = []
    for row in triage:
        ts = row.get("first_seen_at", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= cutoff:
                recent.append(row)
        except Exception:
            recent.append(row)

    if not recent:
        print(f"  None in last {days} days.")
        return

    for row in sorted(recent, key=lambda x: x.get("first_seen_at", ""), reverse=True):
        ticker  = row.get("ticker", "?")
        cat     = row.get("event_category", "")
        impact  = row.get("impact_score", "?")
        distress= row.get("distress_score", "?")
        state   = row.get("alert_state", "?")
        seen    = _since(row.get("first_seen_at", ""))
        alerted = _since(row.get("last_alerted_at", "")) if row.get("last_alerted_at") else "not sent"
        title   = (row.get("title", "") or "")[:60]
        state_icon = "✓" if state == "SENT" else "○" if state == "NEW" else "—"
        print(f"  {state_icon} {ticker:<8} {cat:<30} impact:{impact}  distress:{distress}")
        print(f"    seen: {seen}  |  alerted: {alerted}")
        print(f"    {title}")


def print_buy_signals(signals: list[dict], days: int) -> None:
    section(f"Buy Signals (last {days} days)")
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    recent = [s for s in signals if s.get("signal_date", "") >= cutoff]
    if not recent:
        print(f"  None in last {days} days.")
        return
    for s in sorted(recent, key=lambda x: x.get("signal_date", ""), reverse=True):
        ticker   = s.get("ticker", "?")
        conf     = s.get("confidence_level", "")
        entry    = s.get("entry_price", "")
        target   = s.get("target_price", "")
        stop     = s.get("stop_loss", "")
        cat      = s.get("event_category", "")
        sdate    = s.get("signal_date", "")
        executed = s.get("executed", "")
        outcome  = s.get("outcome", "")
        exec_str = f"  executed: {s.get('execution_price')} on {s.get('execution_date')}" if executed else "  not executed"
        outcome_str = f"  outcome: {outcome}" if outcome else ""
        print(f"  {sdate}  {ticker:<8} {conf:<8} {cat}")
        print(f"    entry: {entry}  stop: {stop}  target: {target}")
        print(f"   {exec_str}{outcome_str}")


def print_cooldown_state(cooldown: dict) -> None:
    section("Alert Cooldown State")
    if not cooldown:
        print("  No active suppressions.")
        return
    now = time.time()
    cfg = _load_json(CONFIG)
    cooldown_hours = (cfg.get("alerts", {}) or {}).get("notification_cooldown", {}).get("cooldown_hours", 4)
    active = []
    for key, sent_at in cooldown.items():
        remaining = (float(sent_at) + cooldown_hours * 3600) - now
        if remaining > 0:
            active.append((key, remaining))
    if not active:
        print("  No active suppressions.")
    else:
        print(f"  {len(active)} ticker(s) currently suppressed:")
        for key, remaining in sorted(active, key=lambda x: -x[1]):
            h = int(remaining // 3600)
            m = int((remaining % 3600) // 60)
            print(f"    {key:<40} expires in {h}h {m}m")


def print_validation_cache(cache: dict) -> None:
    section("Haiku Validation Cache")
    if not cache:
        print("  Empty (freshly cleared or no agent validations yet).")
        return
    statuses: dict[str, int] = {}
    for v in cache.values():
        verdict = v.get("verdict", {}) if isinstance(v, dict) else {}
        s = verdict.get("validation_status", "unknown") if isinstance(verdict, dict) else "unknown"
        statuses[s] = statuses.get(s, 0) + 1
    total = len(cache)
    approved = statuses.get("approved", 0)
    rejected = statuses.get("rejected", 0)
    print(f"  Total cached verdicts: {total}")
    print(f"  Approved:  {approved}  ({_pct(approved, total)})")
    print(f"  Rejected:  {rejected}  ({_pct(rejected, total)})")


def print_flags(hb: dict, watchlist: list[dict]) -> None:
    section("Flags / Attention")
    flags = []

    # analysis errors on active watches
    db = hb.get("summary", {}).get("dropoff_breakdown", {})
    if db.get("analysis_errors", 0) > 0:
        flags.append(f"analysis_error on {db['analysis_errors']} watch(es) last cycle — check Tiingo token or price data")

    # container error
    if hb.get("error"):
        flags.append(f"Container error: {hb['error'][:80]}")

    # watches not checked recently
    stale_cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    for w in watchlist:
        if w.get("status", "").upper() != "ACTIVE":
            continue
        lc = w.get("last_checked_at", "")
        if not lc:
            flags.append(f"{w.get('ticker')} watch has never been checked")
            continue
        try:
            dt = datetime.fromisoformat(lc.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < stale_cutoff:
                flags.append(f"{w.get('ticker')} watch last checked {_since(lc)} — container may be stuck")
        except Exception:
            pass

    if not flags:
        print("  ✓  Nothing needs attention.")
    else:
        for f in flags:
            print(f"  ⚠  {f}")


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Catastrophe Analyzer daily review")
    parser.add_argument("--days", type=int, default=7, help="Lookback window in days (default: 7)")
    args = parser.parse_args()

    hb       = _load_json(DATA_DIR / "runtime_heartbeat.json")
    watchlist= _load_csv(DATA_DIR / "event_watchlist.csv")
    triage   = _load_csv(DATA_DIR / "event_triage.csv")
    signals  = _load_csv(DATA_DIR / "buy_signals.csv")
    cooldown = _load_json(DATA_DIR / "alert_cooldown_state.json")
    val_cache= _load_json(DATA_DIR / "entity_validation_cache.json")

    print_header(hb)
    print_pipeline_health(hb)
    print_tiingo_utilization(hb)
    print_active_watches(watchlist)
    print_high_value_events(triage, args.days)
    print_buy_signals(signals, args.days)
    print_cooldown_state(cooldown)
    print_validation_cache(val_cache)
    print_flags(hb, watchlist)
    print()


if __name__ == "__main__":
    main()
