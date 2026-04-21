"""
Signal quality diagnostic report for catastrophe-analyzer.

Reads data files and produces a funnel breakdown showing exactly where
potential signals are dying and whether the gate thresholds look calibrated.

Usage:
    python scripts/signal_diagnostic.py           # last 14 days
    python scripts/signal_diagnostic.py --days 30
    python scripts/signal_diagnostic.py --days 7 --wide
"""

import argparse
import csv
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent / "data"
CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.json"


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


def _float(val, default=0.0) -> float:
    try:
        return float(val) if val not in (None, "", "None") else default
    except (ValueError, TypeError):
        return default


def _cutoff(days: int) -> str:
    return (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")


def _bar(value: float, total: float, width: int = 20) -> str:
    if total <= 0:
        return " " * width
    filled = int(round((value / total) * width))
    return "█" * filled + "░" * (width - filled)


def _pct(num, den) -> str:
    if not den:
        return "  n/a"
    return f"{100 * num / den:5.1f}%"


# ── sections ─────────────────────────────────────────────────────────────────

def section_funnel(heartbeat: dict, days: int) -> None:
    summary = heartbeat.get("summary", {})
    dropoff = summary.get("dropoff_breakdown", {})
    print(f"\n{'─'*60}")
    print("  PIPELINE FUNNEL  (last heartbeat cycle)")
    print(f"{'─'*60}")

    articles     = summary.get("articles", 0)
    val_drops    = summary.get("skipped_unapproved_validation", 0)
    dist_drops   = summary.get("skipped_low_distress", 0)
    dup_drops    = summary.get("skipped_duplicate_article_ticker", 0)
    watches_made = summary.get("watches_created", 0)
    analyses_req = dropoff.get("analyses_requested", 0)
    analyses_ret = dropoff.get("analyses_returned", 0)
    anal_errors  = dropoff.get("analysis_errors", 0)
    rule_pass    = dropoff.get("rule_passed_candidates", 0)
    signals_saved = summary.get("signals_saved", 0)

    rows = [
        ("Articles scanned",           articles,     articles),
        ("→ Dropped: entity validation", val_drops,  articles),
        ("→ Dropped: low distress",      dist_drops, articles),
        ("→ Dropped: duplicate",         dup_drops,  articles),
        ("→ Watches created",            watches_made, articles),
        ("→ Analyses requested",         analyses_req, articles),
        ("  ↳ Errors (Tiingo/data)",      anal_errors,  analyses_req or 1),
        ("  ↳ Rule passed",               rule_pass,    analyses_req or 1),
        ("→ Signals saved",               signals_saved, articles),
    ]
    for label, val, denom in rows:
        pct = _pct(val, denom)
        print(f"  {label:<35} {val:>6,}  {pct}")

    gate_rejections = summary.get("gate_rejections_by_reason", {})
    if gate_rejections:
        print(f"\n  Gate rejections this cycle:")
        for reason, count in sorted(gate_rejections.items(), key=lambda x: -x[1]):
            print(f"    {reason:<45} {count:>4}")


def section_watches(watchlist: list[dict], days: int) -> None:
    print(f"\n{'─'*60}")
    print(f"  ACTIVE WATCHES")
    print(f"{'─'*60}")
    active = [w for w in watchlist if w.get("status") == "ACTIVE"]
    expired = [w for w in watchlist if w.get("status") == "EXPIRED"]
    signaled = [w for w in watchlist if w.get("status") == "SIGNAL_CREATED"]
    print(f"  Active: {len(active)}   Expired: {len(expired)}   Signaled: {len(signaled)}   Total: {len(watchlist)}")
    if active:
        print()
        print(f"  {'TICKER':<8} {'CATEGORY':<28} {'EVENT DATE':<12} {'DISTRESS':>8}  LAST CHECKED")
        for w in sorted(active, key=lambda x: x.get("event_date", ""), reverse=True):
            lc = (w.get("last_checked_at") or "")[:16]
            print(
                f"  {w.get('ticker','?'):<8} "
                f"{w.get('event_category','?'):<28} "
                f"{w.get('event_date','?'):<12} "
                f"{w.get('distress_score','?'):>8}  "
                f"{lc}"
            )


def section_gate_rejections(analyses: list[dict], days: int) -> None:
    cutoff = _cutoff(days)
    recent = [
        a for a in analyses
        if (a.get("analysis_date") or a.get("event_date") or "") >= cutoff
    ]

    print(f"\n{'─'*60}")
    print(f"  SIGNAL GATE REJECTIONS  (last {days} days, {len(recent)} analyses)")
    print(f"{'─'*60}")

    if not recent:
        print("  No analysis data yet — gates will populate as watches accumulate.")
        print("  Come back after a few days of the fixed entity extractor running.")
        return

    reason_counts = Counter(a.get("signal_decision_reason", "unknown") for a in recent)
    total = len(recent)

    print(f"\n  {'REJECTION REASON':<48} {'COUNT':>5}  {'%':>6}  BAR")
    for reason, count in reason_counts.most_common():
        decision = "SIGNAL" if reason in ("", None) else "rejected"
        bar = _bar(count, total, 18)
        pct = _pct(count, total)
        marker = "✓" if reason == "SIGNAL" or reason == "" else "✗"
        print(f"  {marker} {reason:<46} {count:>5}  {pct}  {bar}")

    # Interpretation hints
    hints = {
        "price_drop_threshold_failed": (
            "DROP TOO SMALL  → consider lowering price_drop_threshold below 10%"
        ),
        "drop_within_48h_threshold_failed": (
            "EOD DATA LAG    → overnight news won't show 48h drop until day-end"
        ),
        "volume_spike_threshold_failed": (
            "LOW VOLUME      → consider lowering volume_spike_threshold below 1.5x"
        ),
        "technical_weakness_condition_failed": (
            "NO TECH SIGNAL  → RSI not oversold AND price not below MA20"
        ),
        "analysis_error": (
            "DATA ERROR      → Tiingo 429 or no price data for event date"
        ),
        "min_catalyst_score_failed": (
            "LOW CATALYST    → distress+impact average below min_catalyst_score_for_signal"
        ),
        "fast_recovery_filter_failed": (
            "FAST RECOVERY   → stock rebounded before recovery_days_threshold"
        ),
        "liquidity_price_floor_failed": (
            "PENNY STOCK     → price < min_price_for_signal (currently $2.50)"
        ),
        "liquidity_volume_floor_failed": (
            "THIN VOLUME     → avg 20d volume < min_avg_volume_for_signal (300k)"
        ),
    }
    active_hints = [h for r, h in hints.items() if r in reason_counts]
    if active_hints:
        print(f"\n  Calibration hints:")
        for h in active_hints:
            print(f"    ⚑  {h}")


def section_price_action(analyses: list[dict], days: int) -> None:
    cutoff = _cutoff(days)
    recent = [
        a for a in analyses
        if (a.get("analysis_date") or a.get("event_date") or "") >= cutoff
        and "error" not in str(a.get("signal_decision_reason", ""))
        and a.get("max_drop_pct") not in (None, "", "0.0", "0")
    ]

    print(f"\n{'─'*60}")
    print(f"  PRICE ACTION ON WATCHED EVENTS  (last {days} days)")
    print(f"{'─'*60}")

    if not recent:
        print("  No price data yet.")
        return

    print(
        f"\n  {'TICKER':<7} {'CAT':<22} {'MAX DROP%':>9} {'48H DROP%':>9} "
        f"{'VOL SPIKE':>9} {'RSI':>5}  DECISION"
    )
    for a in sorted(recent, key=lambda x: _float(x.get("max_drop_pct")), reverse=True):
        reason = a.get("signal_decision_reason") or a.get("signal_decision") or "?"
        marker = "✓" if a.get("signal_decision") in ("SIGNAL", "BUY") else "✗"
        print(
            f"  {marker} {a.get('ticker','?'):<6} "
            f"{a.get('event_category','?')[:21]:<22} "
            f"{_float(a.get('max_drop_pct')):>8.1f}% "
            f"{_float(a.get('drop_48h_pct')):>8.1f}% "
            f"{_float(a.get('volume_spike_at_event')):>8.2f}x "
            f"{_float(a.get('current_rsi', 50)):>5.1f}  "
            f"{reason[:35]}"
        )

    # Summary stats
    drops = [_float(a.get("max_drop_pct")) for a in recent]
    drops_48h = [_float(a.get("drop_48h_pct")) for a in recent]
    if drops:
        print(f"\n  Max drop range: {min(drops):.1f}% – {max(drops):.1f}%   "
              f"median: {sorted(drops)[len(drops)//2]:.1f}%")
        missed_by_drop = sum(1 for d in drops if 0 < d < 10)
        if missed_by_drop:
            print(f"  ⚑  {missed_by_drop} event(s) dropped 1–9% — might be real signals at a lower threshold")


def section_triage(triage: list[dict], days: int) -> None:
    cutoff = _cutoff(days)
    recent = [t for t in triage if (t.get("first_seen_at") or "") >= cutoff]

    print(f"\n{'─'*60}")
    print(f"  RECENT TRIAGED EVENTS  (last {days} days, {len(recent)} events)")
    print(f"{'─'*60}")

    if not recent:
        print("  No triage events in window.")
        return

    cat_counts = Counter(t.get("event_category") for t in recent)
    print(f"\n  By category:")
    for cat, count in cat_counts.most_common():
        print(f"    {cat:<35} {count:>4}")

    print(f"\n  {'TICKER':<8} {'CATEGORY':<28} {'DISTRESS':>8} {'IMPACT':>7}  STATUS")
    for t in sorted(recent, key=lambda x: x.get("first_seen_at",""), reverse=True)[:20]:
        print(
            f"  {t.get('ticker','?'):<8} "
            f"{t.get('event_category','?'):<28} "
            f"{t.get('distress_score','?'):>8} "
            f"{t.get('impact_score','?'):>7}  "
            f"{t.get('validation_status','?')}"
        )


def section_config_snapshot() -> None:
    cfg = _load_json(CONFIG_PATH)
    signals_cfg = cfg.get("signals", {})

    print(f"\n{'─'*60}")
    print("  CURRENT GATE THRESHOLDS  (from settings.json)")
    print(f"{'─'*60}")

    if not signals_cfg:
        print("  signals config not found.")
        return

    defaults = {k: v for k, v in signals_cfg.items() if k != "by_category" and k != "confidence_levels"}
    by_cat = signals_cfg.get("by_category", {})
    watch_days = cfg.get("breach_watch", cfg.get("event_watch", {})).get("max_days", "?")

    print(f"\n  Defaults:   drop>{defaults.get('price_drop_threshold','?')}%  "
          f"vol>{defaults.get('volume_spike_threshold','?')}x  "
          f"rsi<{defaults.get('rsi_oversold_threshold','?')}  "
          f"48h_drop>{defaults.get('drop_within_48h_threshold','?')}%  "
          f"watch_window={watch_days}d")

    if by_cat:
        print(f"\n  {'CATEGORY':<35} {'DROP%':>6} {'VOL':>5} {'RSI':>5} {'48H%':>5}")
        print(f"  {'─'*35} {'─'*6} {'─'*5} {'─'*5} {'─'*5}")
        for cat, t in sorted(by_cat.items()):
            flag = ""
            drop = t.get('price_drop_threshold', 0)
            vol  = t.get('volume_spike_threshold', 0)
            # Flag categories with thresholds that look very hard to hit
            if drop >= 15 or vol >= 2.0:
                flag = " ⚑ high"
            print(
                f"  {cat:<35} {drop:>5}% {vol:>4}x {t.get('rsi_oversold_threshold','?'):>5} "
                f"{t.get('drop_within_48h_threshold','?'):>4}%{flag}"
            )


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Catastrophe analyzer signal diagnostic")
    parser.add_argument("--days", type=int, default=14, help="Lookback window in days (default 14)")
    args = parser.parse_args()
    days = args.days

    heartbeat  = _load_json(DATA_DIR / "runtime_heartbeat.json")
    watchlist  = _load_csv(DATA_DIR / "event_watchlist.csv")
    analyses   = _load_csv(DATA_DIR / "analysis_results.csv")
    triage     = _load_csv(DATA_DIR / "event_triage.csv")
    signals    = _load_csv(DATA_DIR / "buy_signals.csv")

    hb_ts = heartbeat.get("timestamp", "unknown")[:19]
    print(f"\n{'═'*60}")
    print(f"  CATASTROPHE ANALYZER — SIGNAL DIAGNOSTIC")
    print(f"  Lookback: {days} days   |   Last heartbeat: {hb_ts}")
    print(f"  Signals all-time: {len(signals)}")
    print(f"{'═'*60}")

    section_funnel(heartbeat, days)
    section_watches(watchlist, days)
    section_triage(triage, days)
    section_gate_rejections(analyses, days)
    section_price_action(analyses, days)
    section_config_snapshot()

    print(f"\n{'═'*60}\n")


if __name__ == "__main__":
    main()
