#!/usr/bin/env python3
"""
Send a 7-day retrospective sample to ntfy using local CSV data + current config thresholds.

Run from repo root (or any cwd): uses paths relative to this file's parent (repo root).

  python3 scripts/send_retrospective_phone_sample.py

Local preview (no phone, copy-paste URLs from disk):

  CATASTROPHE_ALERTS_LOCAL_ONLY=1 python3 scripts/send_retrospective_phone_sample.py

Writes under data/alert_previews/ (see config/alerts_config.json local_alert_preview).
"""

from __future__ import annotations

import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "src"
sys.path.insert(0, str(SRC))

os.chdir(SRC)  # match monitor.py relative paths

from alert_manager import AlertManager  # noqa: E402
from signal_generator import SignalGenerator  # noqa: E402


def _parse_ymd(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime((s or "").strip(), "%Y-%m-%d")
    except ValueError:
        return None


def _parse_int(s: str, default: int = 0) -> int:
    try:
        return int(float((s or "").strip()))
    except (TypeError, ValueError):
        return default


def _read_csv(path: Path) -> List[Dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _event_lookup(events: List[Dict]) -> Dict[Tuple[str, str, str], Dict]:
    """First event row per (ticker, event_date, event_category)."""
    out: Dict[Tuple[str, str, str], Dict] = {}
    for row in events:
        key = (
            (row.get("ticker") or "").strip().upper(),
            (row.get("event_date") or "").strip(),
            (row.get("event_category") or "").strip(),
        )
        if key[0] and key[1] and key not in out:
            out[key] = row
    return out


def _merge_triage_row(triage: Dict, ev: Optional[Dict]) -> Dict:
    title = (triage.get("title") or "").strip()
    url = (triage.get("url") or "").strip()
    summary = (triage.get("impact_summary") or "").strip()
    if ev:
        if not title:
            title = (ev.get("event_subtype") or ev.get("summary") or "")[:120].strip()
        if not url:
            url = (ev.get("url") or "").strip()
        if ev.get("summary") and len((summary or "")) < 40:
            summary = (ev.get("summary") or summary)[:500]
    return {
        "event_key": triage.get("event_key", ""),
        "ticker": triage.get("ticker", ""),
        "company": triage.get("company", ""),
        "event_date": triage.get("event_date", ""),
        "event_category": triage.get("event_category", ""),
        "event_subtype": triage.get("event_subtype", ""),
        "distress_score": _parse_int(triage.get("distress_score", "")),
        "distress_likelihood": triage.get("distress_likelihood", ""),
        "impact_score": _parse_int(triage.get("impact_score", "")),
        "impact_likelihood": triage.get("impact_likelihood", ""),
        "impact_summary": summary,
        "title": title,
        "url": url,
    }


def _analysis_to_signal_input(row: Dict) -> Dict:
    cur_rsi = float(row.get("current_rsi") or 50)
    rec = row.get("recovery_days", "").strip()
    recovery = None if not rec else int(float(rec)) if rec.replace(".", "").isdigit() else None
    return {
        "ticker": row.get("ticker", ""),
        "event_date": row.get("event_date", ""),
        "event_category": row.get("event_category", ""),
        "pre_event_price": float(row.get("pre_event_price") or 0),
        "current_price": float(row.get("current_price") or 0),
        "min_price_post_event": float(row.get("min_price_post_event") or 0),
        "max_drop_pct": float(row.get("max_drop_pct") or 0),
        "recovery_days": recovery,
        "current_rsi": cur_rsi,
        "event_rsi": cur_rsi,
        "rsi_oversold": cur_rsi < 28,
        "price_below_ma20": cur_rsi < 35,
        "volume_spike_at_event": float(row.get("volume_spike_at_event") or 0),
    }


def main() -> None:
    settings_path = REPO_ROOT / "config" / "settings.json"
    with settings_path.open(encoding="utf-8") as f:
        settings = json.load(f)

    triage_cfg = settings.get("triage", {})
    min_imp_alert = _parse_int(str(triage_cfg.get("min_impact_score_for_alert", 60)), 60)
    min_dis_alert = _parse_int(str(triage_cfg.get("min_distress_score_for_alert", 35)), 35)
    min_imp_sig = _parse_int(str(triage_cfg.get("min_impact_score_for_signal", 75)), 75)
    min_dis_sig = _parse_int(str(triage_cfg.get("min_distress_score_for_signal", 60)), 60)

    today = datetime.now().date()
    start = today - timedelta(days=7)
    start_s = start.strftime("%Y-%m-%d")
    today_s = today.strftime("%Y-%m-%d")

    data_dir = REPO_ROOT / "data"
    triage_rows = _read_csv(data_dir / "event_triage.csv")
    event_rows = _read_csv(data_dir / "events.csv")
    analysis_rows = _read_csv(data_dir / "analysis_results.csv")

    ev_map = _event_lookup(event_rows)

    in_window = []
    for tr in triage_rows:
        ed = _parse_ymd(tr.get("event_date", ""))
        if ed is None or ed.date() < start or ed.date() > today:
            continue
        key = (
            (tr.get("ticker") or "").strip().upper(),
            (tr.get("event_date") or "").strip(),
            (tr.get("event_category") or "").strip(),
        )
        merged = _merge_triage_row(tr, ev_map.get(key))
        in_window.append(merged)

    high_value = [
        r
        for r in in_window
        if r["impact_score"] >= min_imp_alert and r["distress_score"] >= min_dis_alert
    ]
    high_value.sort(
        key=lambda x: (x["impact_score"] + x["distress_score"], x["impact_score"]),
        reverse=True,
    )
    max_hv = 25
    hv_trimmed = len(high_value) - max_hv
    high_value = high_value[:max_hv]

    analysis_by_key = {}
    for ar in analysis_rows:
        k = (
            (ar.get("ticker") or "").strip().upper(),
            (ar.get("event_date") or "").strip(),
            (ar.get("event_category") or "").strip(),
        )
        if k[0] and k[1]:
            analysis_by_key[k] = ar

    gen = SignalGenerator(config_path=str(REPO_ROOT / "config" / "settings.json"))
    synthetic_signals: List[Dict] = []
    for r in in_window:
        if r["impact_score"] < min_imp_sig or r["distress_score"] < min_dis_sig:
            continue
        k = (
            (r["ticker"] or "").strip().upper(),
            (r["event_date"] or "").strip(),
            (r["event_category"] or "").strip(),
        )
        ar = analysis_by_key.get(k)
        if not ar:
            continue
        analysis = _analysis_to_signal_input(ar)
        sig = gen.generate_buy_signal(analysis)
        if not sig:
            continue
        min_conf = float(gen.signal_config.get("min_confidence_for_signal", 0.7))
        thr = min_conf * 100 if min_conf <= 1 else min_conf
        if float(sig.get("confidence", 0)) < thr:
            continue
        sig.setdefault("title", r.get("title", ""))
        sig.setdefault("url", r.get("url", ""))
        sig.setdefault("issue_summary", r.get("impact_summary", ""))
        sig.setdefault("event_subtype", r.get("event_subtype", ""))
        synthetic_signals.append(sig)

    alerts = AlertManager(str(REPO_ROOT / "config" / "alerts_config.json"))
    ntfy_cfg = (alerts.config or {}).get("alert_channels", {}).get("ntfy", {})

    intro = (
        f"*** 7-DAY PHONE SAMPLE (retrospective) ***\n\n"
        f"Window: {start_s} → {today_s} (local data/ CSVs)\n"
        f"High-value filter: impact≥{min_imp_alert}, distress≥{min_dis_alert}\n"
        f"Buy-signal filter: same triage ≥{min_imp_sig}/{min_dis_sig} + "
        f"current SignalGenerator rules + confidence floor\n\n"
        f"Triage rows in window: {len(in_window)}\n"
        f"High-value notifications (capped {max_hv}): {len(high_value)}"
        + (f"  (+{hv_trimmed} more not shown)" if hv_trimmed > 0 else "")
        + "\n"
        f"Buy-style notifications: {len(synthetic_signals)}\n\n"
        f"Use this only for message layout / feedback — not live detection."
    )
    alerts._post_ntfy(
        title=f"Catastrophe Analyzer: 7d sample ({len(high_value)} HV, {len(synthetic_signals)} buys)",
        message=intro,
        cfg=ntfy_cfg,
    )

    if high_value:
        alerts.send_high_value_event_alerts(high_value)
    else:
        alerts._post_ntfy(
            title="Catastrophe Analyzer: 7d sample — no high-value rows",
            message=(
                f"No triage rows in {start_s}..{today_s} met impact≥{min_imp_alert} "
                f"and distress≥{min_dis_alert} in event_triage.csv."
            ),
            cfg=ntfy_cfg,
        )

    if synthetic_signals:
        alerts.send_buy_signal_alerts(synthetic_signals)
    else:
        alerts._post_ntfy(
            title="Catastrophe Analyzer: 7d sample — no buy signals",
            message=(
                "No rows in the window passed strict triage + technical signal rules "
                "using analysis_results.csv (buy_signals.csv was empty)."
            ),
            cfg=ntfy_cfg,
        )

    print("Done. Check ntfy topic for retrospective messages.")


if __name__ == "__main__":
    main()
