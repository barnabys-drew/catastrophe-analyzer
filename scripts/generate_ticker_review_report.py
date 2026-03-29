#!/usr/bin/env python3
"""
Build a Markdown report: one section per (ticker, event_date, event_category) in the lookback window,
so you can review follow-up, legitimacy, and signal quality in Cursor (no phone).

Data: data/event_triage.csv (+ merge events, analysis, signals, watchlist).

  .venv/bin/python scripts/generate_ticker_review_report.py --days 7
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA = REPO_ROOT / "data"
REVIEW_DIR = REPO_ROOT / "review_sessions"
SETTINGS = REPO_ROOT / "config" / "settings.json"


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


def _read_csv(name: str) -> List[Dict[str, str]]:
    path = DATA / name
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _md_escape_line(s: str) -> str:
    return (s or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _md_block(s: str) -> str:
    t = _md_escape_line(s)
    if not t:
        return "_None_\n"
    return "\n".join(f"> {line}" if line else ">" for line in t.split("\n")) + "\n"


def _slug(ticker: str, event_date: str, category: str) -> str:
    raw = f"{ticker}-{event_date}-{category}".lower()
    return re.sub(r"[^a-z0-9]+", "-", raw).strip("-")


def _event_map(events: List[Dict]) -> Dict[Tuple[str, str, str], Dict]:
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


def _best_triage(rows: List[Dict]) -> Dict:
    """Highest impact_score + distress_score wins."""
    best = None
    best_score = -1
    for r in rows:
        a = _parse_int(r.get("impact_score", ""))
        b = _parse_int(r.get("distress_score", ""))
        s = a + b
        if s >= best_score:
            best_score = s
            best = r
    return best or rows[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-ticker Markdown review report.")
    parser.add_argument("--days", type=int, default=7, help="Lookback days for event_date (default 7)")
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Output .md path (default: review_sessions/ticker-review-TIMESTAMP.md)",
    )
    args = parser.parse_args()

    today = datetime.now().date()
    start = today - timedelta(days=max(1, int(args.days)))
    start_s = start.strftime("%Y-%m-%d")
    today_s = today.strftime("%Y-%m-%d")

    triage = _read_csv("event_triage.csv")
    events = _read_csv("events.csv")
    analysis = _read_csv("analysis_results.csv")
    signals = _read_csv("buy_signals.csv")
    watches = _read_csv("event_watchlist.csv")

    ev_map = _event_map(events)

    by_key: Dict[Tuple[str, str, str], List[Dict]] = {}
    for row in triage:
        ed = _parse_ymd(row.get("event_date", ""))
        if ed is None:
            continue
        d = ed.date()
        if d < start or d > today:
            continue
        key = (
            (row.get("ticker") or "").strip().upper(),
            (row.get("event_date") or "").strip(),
            (row.get("event_category") or "").strip(),
        )
        if not key[0] or not key[1]:
            continue
        by_key.setdefault(key, []).append(row)

    merged: List[Tuple[Tuple[str, str, str], Dict]] = []
    for key, rows in by_key.items():
        merged.append((key, _best_triage(rows)))

    merged.sort(key=lambda x: (x[0][1], x[0][0], x[0][2]), reverse=True)

    analysis_by_key: Dict[Tuple[str, str, str], Dict] = {}
    for row in analysis:
        k = (
            (row.get("ticker") or "").strip().upper(),
            (row.get("event_date") or "").strip(),
            (row.get("event_category") or "").strip(),
        )
        if k[0] and k[1]:
            analysis_by_key[k] = row

    signal_by_key: Dict[Tuple[str, str, str], Dict] = {}
    for row in signals:
        if not (row.get("ticker") or "").strip():
            continue
        k = (
            (row.get("ticker") or "").strip().upper(),
            (row.get("event_date") or "").strip(),
            (row.get("event_category") or "").strip(),
        )
        if k[0] and k[1]:
            signal_by_key[k] = row

    watch_by_key: Dict[Tuple[str, str, str], Dict] = {}
    for row in watches:
        k = (
            (row.get("ticker") or "").strip().upper(),
            (row.get("event_date") or "").strip(),
            (row.get("event_category") or "").strip(),
        )
        if k[0] and k[1]:
            watch_by_key[k] = row

    thresholds = {}
    if SETTINGS.exists():
        try:
            thresholds = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            thresholds = {}

    triage_cfg = thresholds.get("triage", {})
    sig_cfg = thresholds.get("signals", {})
    entity_cfg = thresholds.get("entity_extraction", {})
    validation_mode = str(entity_cfg.get("validation_mode", "strict_rules") or "strict_rules").strip().lower()
    agent_cfg = entity_cfg.get("agent_validation", {}) or {}
    thr_lines = [
        f"- High-value alert bar: impact ≥ {triage_cfg.get('min_impact_score_for_alert', 60)}, "
        f"distress ≥ {triage_cfg.get('min_distress_score_for_alert', 35)}",
        f"- Persisted signal triage bar: impact ≥ {triage_cfg.get('min_impact_score_for_signal', 75)}, "
        f"distress ≥ {triage_cfg.get('min_distress_score_for_signal', 60)}",
        f"- Signal confidence floor: min_confidence_for_signal = {sig_cfg.get('min_confidence_for_signal', 'n/a')}",
        f"- Entity validation mode: `{validation_mode}`",
        f"- Agent fail-closed: `{agent_cfg.get('fail_closed', True)}`",
    ]

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = Path(args.output) if args.output else REVIEW_DIR / f"ticker-review-{stamp}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    lines: List[str] = [
        f"# Ticker review report",
        f"",
        f"- **Window:** `{start_s}` → `{today_s}` (event_date in triage)",
        f"- **Generated:** {datetime.now().isoformat()}",
        f"- **Rows:** {len(merged)} distinct (ticker, event_date, event_category)",
        f"",
        f"## Current thresholds (from config/settings.json)",
        *thr_lines,
        f"",
        f"## How to use",
        f"",
        f"1. Open this file in Cursor.",
        f"2. For each ticker block, open the **Article URL** in a browser (copy from the line or use local alert preview `data/alert_previews/` if you ran with `CATASTROPHE_ALERTS_LOCAL_ONLY=1`).",
        f"3. Fill the **Your review** checklists and notes.",
        f"",
        f"---",
        f"",
        f"## Summary table",
        f"",
        f"| Ticker | Event date | Category | Impact | Distress | Validation | Analysis | Signal | Meets HV bar | Meets signal triage bar |",
        f"|--------|------------|----------|--------|----------|------------|----------|--------|--------------|-------------------------|",
    ]

    mi_a = _parse_int(str(triage_cfg.get("min_impact_score_for_alert", 60)))
    md_a = _parse_int(str(triage_cfg.get("min_distress_score_for_alert", 35)))
    mi_s = _parse_int(str(triage_cfg.get("min_impact_score_for_signal", 75)))
    md_s = _parse_int(str(triage_cfg.get("min_distress_score_for_signal", 60)))

    toc: List[str] = ["## Table of contents", ""]
    for key, tr in merged:
        ticker, event_date, cat = key
        slug = _slug(ticker, event_date, cat)
        toc.append(f"- [{ticker} — {event_date} — {cat}](#{slug})")
    toc.extend(["", "---", ""])

    for key, tr in merged:
        ticker, event_date, cat = key
        slug = _slug(ticker, event_date, cat)
        ev = ev_map.get(key)
        an = analysis_by_key.get(key)
        sg = signal_by_key.get(key)
        w = watch_by_key.get(key)

        imp = _parse_int(tr.get("impact_score", ""))
        dis = _parse_int(tr.get("distress_score", ""))
        hv_ok = "Yes" if imp >= mi_a and dis >= md_a else "No"
        sig_tri_ok = "Yes" if imp >= mi_s and dis >= md_s else "No"
        validation_status = (tr.get("validation_status") or "").strip().lower()
        validation_cell = validation_status.upper() if validation_status else "N/A"

        url_triage = (tr.get("url") or "").strip()
        title_triage = (tr.get("title") or "").strip()
        if ev:
            url_ev = (ev.get("url") or "").strip()
            sum_ev = (ev.get("summary") or "").strip()
            if not url_triage and url_ev:
                url_triage = url_ev
            if not title_triage and sum_ev:
                title_triage = (sum_ev[:100] + "…") if len(sum_ev) > 100 else sum_ev

        lines.append(
            f"| {ticker} | {event_date} | {cat} | {imp} | {dis} | "
            f"{validation_cell} | {'Yes' if an else 'No'} | {'Yes' if sg else 'No'} | {hv_ok} | {sig_tri_ok} |"
        )

    lines.extend(["", "---", ""] + toc)

    for key, tr in merged:
        ticker, event_date, cat = key
        slug = _slug(ticker, event_date, cat)
        ev = ev_map.get(key)
        an = analysis_by_key.get(key)
        sg = signal_by_key.get(key)
        w = watch_by_key.get(key)

        imp = _parse_int(tr.get("impact_score", ""))
        dis = _parse_int(tr.get("distress_score", ""))

        url_triage = (tr.get("url") or "").strip()
        title_triage = (tr.get("title") or "").strip()
        if ev:
            url_ev = (ev.get("url") or "").strip()
            sum_ev = (ev.get("summary") or "").strip()
            if not url_triage and url_ev:
                url_triage = url_ev
            if not title_triage and sum_ev:
                title_triage = (sum_ev[:120] + "…") if len(sum_ev) > 120 else sum_ev

        lines.extend(
            [
                f'<a id="{slug}"></a>',
                f"",
                f"## {ticker} — {event_date} — {cat}",
                f"",
                f"### Triage (event_triage.csv)",
                f"",
                f"| Field | Value |",
                f"|-------|-------|",
                f"| Company | {tr.get('company', '')} |",
                f"| Subtype | {tr.get('event_subtype', '')} |",
                f"| Distress | {tr.get('distress_likelihood', '')} ({tr.get('distress_score', '')}/100) |",
                f"| Impact | {tr.get('impact_likelihood', '')} ({tr.get('impact_score', '')}/100) |",
                f"| Validation | {tr.get('validation_status', '')} via {tr.get('validation_engine', '')} |",
                f"| Validation confidence | {tr.get('validation_confidence', '')} |",
                f"| Alert state | {tr.get('alert_state', '')} |",
                f"| Triage engine | {tr.get('triage_engine', '')} |",
                f"",
                f"**Validation reason**",
                f"",
                _md_block(tr.get("validation_reason", "")),
                f"",
                f"**Impact summary**",
                f"",
                _md_block(tr.get("impact_summary", "")),
                f"",
                f"**Article title (if stored)**",
                f"",
                _md_block(title_triage),
                f"",
                f"**Article URL (copy-paste)**",
                f"",
            ]
        )
        if url_triage:
            lines.append(f"```text")
            lines.append(url_triage)
            lines.append(f"```")
        else:
            lines.append("_No URL in triage/events for this key — check watchlist or re-ingest._")
        lines.append("")

        lines.extend(
            [
                f"### Event record (events.csv)",
                f"",
            ]
        )
        if ev:
            lines.append(f"- Source: `{ev.get('source', '')}`")
            lines.append(f"- Severity: `{ev.get('severity', '')}`")
            lines.append(f"- Summary excerpt:")
            lines.append(_md_block(ev.get("summary", "")))
        else:
            lines.append("_No matching events.csv row for this (ticker, event_date, event_category)._")
        lines.append("")

        lines.extend(
            [
                f"### Watchlist (event_watchlist.csv)",
                f"",
            ]
        )
        if w:
            lines.append(
                f"| Status | URL | Source | Distress |"
            )
            lines.append(f"|--------|-----|--------|----------|")
            lines.append(
                f"| {w.get('status', '')} | `{w.get('url', '')}` | {w.get('source', '')} | "
                f"{w.get('distress_likelihood', '')} ({w.get('distress_score', '')}) |"
            )
        else:
            lines.append("_No watch row for this key._")
        lines.append("")

        lines.extend([f"### Price / technical (analysis_results.csv)", f""])
        if an:
            lines.append(
                f"| max_drop_pct | current_rsi | vol spike | pre → current | min post | recovery_days |"
            )
            lines.append(f"|--------------|-------------|-----------|---------------|----------|---------------|")
            lines.append(
                f"| {an.get('max_drop_pct', '')} | {an.get('current_rsi', '')} | {an.get('volume_spike_at_event', '')} | "
                f"{an.get('pre_event_price', '')} → {an.get('current_price', '')} | {an.get('min_price_post_event', '')} | "
                f"{an.get('recovery_days', '')} |"
            )
            lines.append(f"")
            lines.append(f"_Analysis date: `{an.get('analysis_date', '')}`_")
        else:
            lines.append("_No analysis row for this key._")
        lines.append("")

        lines.extend([f"### Buy signal (buy_signals.csv)", f""])
        if sg:
            lines.append(
                f"| Type | Conf | Entry | Stop | Target | RR | Executed | Outcome |"
            )
            lines.append(f"|------|------|-------|------|--------|----|---------|--------|")
            lines.append(
                f"| {sg.get('signal_type', '')} | {sg.get('confidence_level', '')} ({sg.get('confidence_score', '')}) | "
                f"{sg.get('entry_price', '')} | {sg.get('stop_loss', '')} | {sg.get('target_price', '')} | "
                f"{sg.get('risk_reward_ratio', '')} | {sg.get('executed', '')} | {sg.get('outcome', '')} |"
            )
        else:
            lines.append("_No persisted buy signal for this key._")
        lines.append("")

        lines.extend(
            [
                f"### Your review",
                f"",
                f"- [ ] **Follow-up:** Opened article / verified company–ticker mapping / timing vs headline",
                f"- [ ] **Legitimacy:** Material event for this name? Correct US listing? Source trustworthy?",
                f"- [ ] **Signal:** Under current rules, would you treat analysis + triage as a *good* candidate or skip? Why?",
                f"",
                f"**Notes:**",
                f"",
                f"_(Write below.)_",
                f"",
                f"",
                f"---",
                f"",
            ]
        )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}")
    print(f"Open in Cursor: {out_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
