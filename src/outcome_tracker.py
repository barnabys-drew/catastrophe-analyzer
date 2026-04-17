"""
Post-signal outcome tracker.

For every emitted signal, this module computes realized returns at T+1, T+5,
T+10, and T+20 trading days (relative to `signal_date`) and records them to a
dedicated CSV so the learning loop can measure win rate by category and
confidence bucket.

Design principles:
- Deterministic: given the same `buy_signals.csv` and the same price histories,
  produces the same rows.
- Idempotent: re-running only appends rows for `(ticker, signal_date)` pairs
  that are not already present in `data/signal_outcomes.csv`.
- Side-effect free by default: callers choose whether to persist. The pure
  computation function is test-friendly and does not require a live price feed.
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple


HORIZON_DAYS: Tuple[int, ...] = (1, 5, 10, 20)
OUTCOME_COLUMNS: List[str] = (
    [
        "recorded_at_utc",
        "ticker",
        "signal_date",
        "event_date",
        "event_category",
        "confidence_level",
        "entry_price",
        "stop_loss",
        "target_price",
        "target_template",
    ]
    + [f"close_t_plus_{d}" for d in HORIZON_DAYS]
    + [f"return_t_plus_{d}_pct" for d in HORIZON_DAYS]
    + [
        "hit_target",
        "hit_stop",
        "horizon_days_observed",
    ]
)


@dataclass
class SignalOutcome:
    ticker: str
    signal_date: str
    event_date: str = ""
    event_category: str = ""
    confidence_level: str = ""
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_price: float = 0.0
    target_template: str = ""
    closes: Dict[int, Optional[float]] = field(default_factory=dict)
    returns_pct: Dict[int, Optional[float]] = field(default_factory=dict)
    hit_target: bool = False
    hit_stop: bool = False
    horizon_days_observed: int = 0

    def as_row(self) -> Dict[str, Any]:
        row: Dict[str, Any] = {
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
            "ticker": self.ticker,
            "signal_date": self.signal_date,
            "event_date": self.event_date,
            "event_category": self.event_category,
            "confidence_level": self.confidence_level,
            "entry_price": f"{float(self.entry_price):.6f}",
            "stop_loss": f"{float(self.stop_loss):.6f}",
            "target_price": f"{float(self.target_price):.6f}",
            "target_template": self.target_template,
            "hit_target": "1" if self.hit_target else "0",
            "hit_stop": "1" if self.hit_stop else "0",
            "horizon_days_observed": int(self.horizon_days_observed),
        }
        for d in HORIZON_DAYS:
            close = self.closes.get(d)
            row[f"close_t_plus_{d}"] = f"{float(close):.6f}" if isinstance(close, (int, float)) else ""
            rp = self.returns_pct.get(d)
            row[f"return_t_plus_{d}_pct"] = f"{float(rp):.4f}" if isinstance(rp, (int, float)) else ""
        return row


PriceHistoryFn = Callable[[str, int], Optional[Dict[str, Any]]]


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: str) -> Optional[datetime]:
    raw = (value or "").strip()
    if not raw:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    # Also accept ISO 8601 with 'Z' suffix.
    if raw.endswith("Z"):
        try:
            dt = datetime.strptime(raw[:-1], "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def compute_outcomes(
    signal: Dict[str, Any],
    history: Optional[Dict[str, Any]],
) -> SignalOutcome:
    """Compute realized outcomes for one signal given its post-signal price history."""
    ticker = str(signal.get("ticker", "")).strip().upper()
    signal_date = str(signal.get("signal_date", "")).strip()
    entry_price = _to_float(signal.get("entry_price") or signal.get("suggested_entry"))
    stop_loss = _to_float(signal.get("stop_loss") or signal.get("suggested_stop_loss"))
    target_price = _to_float(signal.get("target_price"))
    target_template = str(signal.get("target_template", "")).strip()

    outcome = SignalOutcome(
        ticker=ticker,
        signal_date=signal_date,
        event_date=str(signal.get("event_date", "")),
        event_category=str(signal.get("event_category", "")),
        confidence_level=str(signal.get("confidence_level", "")),
        entry_price=entry_price,
        stop_loss=stop_loss,
        target_price=target_price,
        target_template=target_template,
    )

    if not history:
        return outcome
    prices = history.get("prices") or []
    dates = history.get("dates") or []
    if not prices or not dates:
        return outcome

    signal_dt = _parse_date(signal_date)
    if signal_dt is None:
        # signal_date may be an event date; try event_date as fallback
        signal_dt = _parse_date(str(signal.get("event_date", "")))
    if signal_dt is None:
        return outcome

    # Find the first bar strictly after signal_date (trading-day alignment).
    start_idx: Optional[int] = None
    for i, d in enumerate(dates):
        try:
            bar_dt = datetime.strptime(str(d), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        if bar_dt > signal_dt:
            start_idx = i
            break
    if start_idx is None:
        return outcome

    max_horizon = max(HORIZON_DAYS)
    entry_base = entry_price if entry_price > 0 else float(prices[start_idx])
    hit_target = False
    hit_stop = False
    horizon_days_observed = 0

    for idx_offset in range(0, max_horizon):
        cursor = start_idx + idx_offset
        if cursor >= len(prices):
            break
        horizon_days_observed = idx_offset + 1
        close = float(prices[cursor])
        if target_price > 0 and close >= target_price:
            hit_target = True
        if stop_loss > 0 and close <= stop_loss:
            hit_stop = True

    for horizon in HORIZON_DAYS:
        target_idx = start_idx + horizon - 1
        if target_idx < len(prices):
            close = float(prices[target_idx])
            outcome.closes[horizon] = close
            if entry_base > 0:
                outcome.returns_pct[horizon] = (close - entry_base) / entry_base * 100.0
            else:
                outcome.returns_pct[horizon] = None
        else:
            outcome.closes[horizon] = None
            outcome.returns_pct[horizon] = None

    outcome.hit_target = hit_target
    outcome.hit_stop = hit_stop
    outcome.horizon_days_observed = horizon_days_observed
    return outcome


def _read_signals(signals_csv: str) -> List[Dict[str, Any]]:
    if not os.path.exists(signals_csv):
        return []
    with open(signals_csv, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_existing_keys(outcomes_csv: str) -> set:
    if not os.path.exists(outcomes_csv):
        return set()
    keys = set()
    with open(outcomes_csv, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            keys.add((row.get("ticker", ""), row.get("signal_date", "")))
    return keys


def _append_row(outcomes_csv: str, row: Dict[str, Any]) -> None:
    new_file = not os.path.exists(outcomes_csv)
    os.makedirs(os.path.dirname(outcomes_csv) or ".", exist_ok=True)
    with open(outcomes_csv, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=OUTCOME_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow({col: row.get(col, "") for col in OUTCOME_COLUMNS})


def update_outcomes(
    signals: Iterable[Dict[str, Any]],
    price_history_fn: PriceHistoryFn,
    outcomes_csv: str,
    history_days: int = 45,
) -> List[SignalOutcome]:
    """Compute outcomes for signals not yet recorded and append to the CSV."""
    seen = _load_existing_keys(outcomes_csv)
    results: List[SignalOutcome] = []
    for signal in signals:
        key = (str(signal.get("ticker", "")), str(signal.get("signal_date", "")))
        if key in seen:
            continue
        history = price_history_fn(str(signal.get("ticker", "")), int(history_days))
        outcome = compute_outcomes(signal, history)
        # Only persist once we have at least one observation horizon.
        if outcome.horizon_days_observed == 0:
            continue
        _append_row(outcomes_csv, outcome.as_row())
        results.append(outcome)
    return results


def update_outcomes_from_files(
    signals_csv: str,
    outcomes_csv: str,
    price_history_fn: PriceHistoryFn,
    history_days: int = 45,
) -> List[SignalOutcome]:
    signals = _read_signals(signals_csv)
    return update_outcomes(signals, price_history_fn, outcomes_csv, history_days=history_days)


def summarize_outcomes(
    outcomes_csv: str,
    horizon: int = 5,
) -> Dict[str, Any]:
    """
    Return per-category and per-confidence win-rate summaries for the given horizon.

    A "win" is a non-negative return at the horizon (inclusive of zero).
    """
    if horizon not in HORIZON_DAYS:
        raise ValueError(f"horizon must be one of {HORIZON_DAYS}")
    if not os.path.exists(outcomes_csv):
        return {
            "samples": 0,
            "by_category": {},
            "by_confidence": {},
            "horizon": horizon,
        }

    by_category: Dict[str, Dict[str, float]] = {}
    by_confidence: Dict[str, Dict[str, float]] = {}
    total = 0
    with open(outcomes_csv, "r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            total += 1
            try:
                r = float(row.get(f"return_t_plus_{horizon}_pct", "") or 0.0)
            except ValueError:
                continue
            category = row.get("event_category", "unknown") or "unknown"
            confidence = row.get("confidence_level", "unknown") or "unknown"

            for bucket_key, bucket in (
                (category, by_category),
                (confidence, by_confidence),
            ):
                entry = bucket.setdefault(bucket_key, {"samples": 0, "wins": 0, "mean_return": 0.0})
                samples = entry["samples"] + 1
                running_mean = entry["mean_return"]
                entry["mean_return"] = running_mean + (r - running_mean) / samples
                entry["samples"] = samples
                if r >= 0.0:
                    entry["wins"] = entry["wins"] + 1

    def _finalize(bucket: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        out: Dict[str, Dict[str, float]] = {}
        for key, entry in bucket.items():
            samples = int(entry["samples"])
            wins = int(entry["wins"])
            win_rate = (wins / samples) if samples else 0.0
            out[key] = {
                "samples": samples,
                "wins": wins,
                "win_rate": round(win_rate, 4),
                "mean_return_pct": round(float(entry["mean_return"]), 4),
            }
        return out

    return {
        "samples": total,
        "horizon": horizon,
        "by_category": _finalize(by_category),
        "by_confidence": _finalize(by_confidence),
    }


__all__ = [
    "HORIZON_DAYS",
    "OUTCOME_COLUMNS",
    "SignalOutcome",
    "compute_outcomes",
    "update_outcomes",
    "update_outcomes_from_files",
    "summarize_outcomes",
]
