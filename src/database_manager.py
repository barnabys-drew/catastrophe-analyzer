"""Database manager for CSV persistence with legacy breach migration support."""

import csv
import json
import os
import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple


class DatabaseManager:
    """Manages CSV-based persistence for event analysis data."""

    EVENTS_FIELDS = [
        "event_date",
        "company",
        "ticker",
        "event_category",
        "event_subtype",
        "distress_likelihood",
        "distress_score",
        "severity",
        "source",
        "url",
        "summary",
        "date_added",
    ]

    ANALYSIS_FIELDS = [
        "ticker",
        "event_date",
        "event_category",
        "pre_event_price",
        "event_anchor_price",
        "current_price",
        "min_price_post_event",
        "max_drop_pct",
        "drop_48h_pct",
        "min_price_post_event_48h",
        "post_event_window_days",
        "recovery_days",
        "current_rsi",
        "volume_spike_at_event",
        "analysis_date",
    ]

    SIGNAL_FIELDS = [
        "signal_date",
        "ticker",
        "event_category",
        "signal_type",
        "confidence_level",
        "confidence_score",
        "entry_price",
        "stop_loss",
        "target_price",
        "risk_reward_ratio",
        "event_date",
        "executed",
        "execution_price",
        "execution_date",
        "outcome",
    ]

    WATCHLIST_FIELDS = [
        "ticker",
        "company",
        "event_date",
        "event_category",
        "event_subtype",
        "distress_likelihood",
        "distress_score",
        "source",
        "url",
        "watch_start_date",
        "last_checked_at",
        "status",
        "timeseries_saved",
    ]

    _DISTRESS_PATTERN = re.compile(
        r"\[Distress\s+(LOW|MEDIUM|HIGH)\s+(\d{1,3})/100\]",
        re.IGNORECASE,
    )

    TIMESERIES_FIELDS = [
        "ticker",
        "event_date",
        "event_category",
        "day_offset",
        "date",
        "close",
        "volume",
    ]

    TRIAGE_FIELDS = [
        "event_key",
        "ticker",
        "company",
        "event_date",
        "event_category",
        "event_subtype",
        "distress_score",
        "distress_likelihood",
        "impact_score",
        "impact_likelihood",
        "impact_summary",
        "url",
        "title",
        "triage_engine",
        "validation_status",
        "validation_reason",
        "validation_confidence",
        "validation_engine",
        "alert_state",
        "first_seen_at",
        "last_seen_at",
        "last_alerted_at",
    ]

    def __init__(self, data_dir: str = "../data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

        # Canonical event paths.
        self.events_file = os.path.join(data_dir, "events.csv")
        self.analysis_file = os.path.join(data_dir, "analysis_results.csv")
        self.signals_file = os.path.join(data_dir, "buy_signals.csv")
        self.watchlist_file = os.path.join(data_dir, "event_watchlist.csv")
        self.timeseries_file = os.path.join(data_dir, "event_price_timeseries.csv")
        self.triage_file = os.path.join(data_dir, "event_triage.csv")

        # Legacy breach paths retained only for migration/fallback.
        self.legacy_breaches_file = os.path.join(data_dir, "breaches.csv")
        self.legacy_watchlist_file = os.path.join(data_dir, "breach_watchlist.csv")
        self.legacy_timeseries_file = os.path.join(data_dir, "breach_price_timeseries.csv")

        # Backward-compatible attributes to reduce churn in other workstreams.
        self.breaches_file = self.events_file

        self._initialize_files()

    def _initialize_files(self) -> None:
        """Create/normalize CSV files and run one-time legacy migration."""
        self._ensure_canonical_csv(
            self.events_file,
            self.EVENTS_FIELDS,
            self._normalize_event_row,
            fallback_path=self.legacy_breaches_file,
        )
        self._ensure_canonical_csv(
            self.analysis_file,
            self.ANALYSIS_FIELDS,
            self._normalize_analysis_row,
        )
        self._ensure_canonical_csv(
            self.signals_file,
            self.SIGNAL_FIELDS,
            self._normalize_signal_row,
        )
        self._ensure_canonical_csv(
            self.watchlist_file,
            self.WATCHLIST_FIELDS,
            self._normalize_watch_row,
            fallback_path=self.legacy_watchlist_file,
        )
        self._ensure_canonical_csv(
            self.timeseries_file,
            self.TIMESERIES_FIELDS,
            self._normalize_timeseries_row,
            fallback_path=self.legacy_timeseries_file,
        )
        self._ensure_canonical_csv(
            self.triage_file,
            self.TRIAGE_FIELDS,
            self._normalize_triage_row,
        )

    def _read_csv(self, path: str) -> Tuple[List[str], List[Dict]]:
        if not os.path.exists(path):
            return [], []
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            return list(reader.fieldnames or []), list(reader)

    def _write_csv(self, path: str, fieldnames: List[str], rows: List[Dict]) -> None:
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    def _ensure_canonical_csv(
        self,
        canonical_path: str,
        canonical_fields: List[str],
        normalize_fn,
        fallback_path: Optional[str] = None,
    ) -> None:
        """Normalize existing CSV schema and migrate from fallback legacy files."""
        current_fields, current_rows = self._read_csv(canonical_path)
        fallback_fields, fallback_rows = ([], [])

        if fallback_path:
            fallback_fields, fallback_rows = self._read_csv(fallback_path)

        use_fallback_rows = not current_rows and bool(fallback_rows)
        needs_rewrite = (
            not os.path.exists(canonical_path)
            or current_fields != canonical_fields
            or use_fallback_rows
        )
        if not needs_rewrite:
            return

        source_rows = fallback_rows if use_fallback_rows else current_rows
        normalized_rows = [normalize_fn(r) for r in source_rows]
        self._write_csv(canonical_path, canonical_fields, normalized_rows)

        # If both files were empty and the path did not exist, ensure header is present.
        if not source_rows and not os.path.exists(canonical_path):
            self._write_csv(canonical_path, canonical_fields, [])

        # Optional migration notice helps operators spot one-time conversions.
        if use_fallback_rows and fallback_path:
            print(
                f"Migrated legacy CSV '{os.path.basename(fallback_path)}' "
                f"-> '{os.path.basename(canonical_path)}'."
            )
        elif fallback_fields and fallback_fields != canonical_fields and fallback_rows and not current_rows:
            print(
                f"Detected legacy schema in '{os.path.basename(fallback_path)}'; "
                f"wrote canonical '{os.path.basename(canonical_path)}'."
            )

    def _normalize_event_row(self, row: Dict) -> Dict:
        distress_likelihood, distress_score = self._extract_distress_fields(row)
        return {
            "event_date": row.get("event_date")
            or row.get("breach_date")
            or row.get("date_found")
            or "",
            "company": row.get("company", ""),
            "ticker": row.get("ticker", ""),
            "event_category": row.get("event_category") or "cybersecurity",
            "event_subtype": row.get("event_subtype") or row.get("breach_type") or "Unknown",
            "distress_likelihood": distress_likelihood,
            "distress_score": distress_score,
            "severity": row.get("severity", "Unknown"),
            "source": row.get("source", ""),
            "url": row.get("url", ""),
            "summary": (row.get("summary") or "")[:500],
            "date_added": row.get("date_added") or datetime.now().isoformat(),
        }

    def _normalize_analysis_row(self, row: Dict) -> Dict:
        return {
            "ticker": row.get("ticker", ""),
            "event_date": row.get("event_date") or row.get("breach_date") or "",
            "event_category": row.get("event_category") or "cybersecurity",
            "pre_event_price": row.get("pre_event_price") or row.get("pre_breach_price") or "",
            "event_anchor_price": row.get("event_anchor_price") or "",
            "current_price": row.get("current_price", ""),
            "min_price_post_event": row.get("min_price_post_event")
            or row.get("min_price_post_breach")
            or "",
            "max_drop_pct": row.get("max_drop_pct", ""),
            "drop_48h_pct": row.get("drop_48h_pct", ""),
            "min_price_post_event_48h": row.get("min_price_post_event_48h", ""),
            "post_event_window_days": row.get("post_event_window_days", ""),
            "recovery_days": row.get("recovery_days", ""),
            "current_rsi": row.get("current_rsi", ""),
            "volume_spike_at_event": row.get("volume_spike_at_event")
            or row.get("volume_spike_at_breach")
            or "",
            "analysis_date": row.get("analysis_date") or datetime.now().isoformat(),
        }

    def _normalize_signal_row(self, row: Dict) -> Dict:
        return {
            "signal_date": row.get("signal_date") or datetime.now().isoformat(),
            "ticker": row.get("ticker", ""),
            "event_category": row.get("event_category") or "cybersecurity",
            "signal_type": row.get("signal_type", ""),
            "confidence_level": row.get("confidence_level", ""),
            "confidence_score": row.get("confidence_score") or row.get("confidence") or "",
            "entry_price": row.get("entry_price") or row.get("suggested_entry") or "",
            "stop_loss": row.get("stop_loss") or row.get("suggested_stop_loss") or "",
            "target_price": row.get("target_price")
            or (row.get("risk_reward", {}) if isinstance(row.get("risk_reward"), dict) else {}).get("target_price", ""),
            "risk_reward_ratio": row.get("risk_reward_ratio")
            or (row.get("risk_reward", {}) if isinstance(row.get("risk_reward"), dict) else {}).get("risk_reward_ratio", ""),
            "event_date": row.get("event_date") or row.get("breach_date") or "",
            "executed": row.get("executed", "No"),
            "execution_price": row.get("execution_price", ""),
            "execution_date": row.get("execution_date", ""),
            "outcome": row.get("outcome", ""),
        }

    def _normalize_watch_row(self, row: Dict) -> Dict:
        distress_likelihood, distress_score = self._extract_distress_fields(row)
        return {
            "ticker": row.get("ticker", ""),
            "company": row.get("company", ""),
            "event_date": row.get("event_date") or row.get("breach_date") or "",
            "event_category": row.get("event_category") or "cybersecurity",
            "event_subtype": row.get("event_subtype") or row.get("breach_type") or "",
            "distress_likelihood": distress_likelihood,
            "distress_score": distress_score,
            "source": row.get("source", ""),
            "url": row.get("url", ""),
            "watch_start_date": row.get("watch_start_date") or datetime.now().strftime("%Y-%m-%d"),
            "last_checked_at": row.get("last_checked_at") or datetime.now().isoformat(),
            "status": row.get("status", "ACTIVE"),
            "timeseries_saved": row.get("timeseries_saved", "No"),
        }

    def _extract_distress_fields(self, row: Dict) -> Tuple[str, str]:
        """Populate distress fields from explicit keys or legacy text tags."""
        likelihood = (row.get("distress_likelihood") or "").upper().strip()
        score = str(row.get("distress_score") or "").strip()

        if likelihood and score:
            return likelihood, score

        text_candidates = [
            row.get("event_subtype", ""),
            row.get("breach_type", ""),
            row.get("summary", ""),
        ]
        for text in text_candidates:
            m = self._DISTRESS_PATTERN.search(str(text or ""))
            if not m:
                continue
            like = (likelihood or m.group(1).upper()).strip()
            val = score or m.group(2)
            try:
                val_int = max(0, min(100, int(val)))
            except ValueError:
                val_int = 0
            return like, str(val_int)

        if likelihood and not score:
            return likelihood, ""
        return "", score

    def _normalize_timeseries_row(self, row: Dict) -> Dict:
        return {
            "ticker": row.get("ticker", ""),
            "event_date": row.get("event_date") or row.get("breach_date") or "",
            "event_category": row.get("event_category") or "cybersecurity",
            "day_offset": row.get("day_offset", ""),
            "date": row.get("date", ""),
            "close": row.get("close", ""),
            "volume": row.get("volume", ""),
        }

    def _normalize_triage_row(self, row: Dict) -> Dict:
        now_iso = datetime.now().isoformat()
        event_key = row.get("event_key") or self.build_event_key(
            ticker=row.get("ticker", ""),
            event_date=row.get("event_date") or row.get("breach_date") or "",
            event_category=row.get("event_category") or "cybersecurity",
            source_url=row.get("url", ""),
            title=row.get("title", ""),
        )
        alert_state = (row.get("alert_state") or "NEW").upper()
        if alert_state not in ("NEW", "SENT", "ACKED", "SUPPRESSED"):
            alert_state = "NEW"
        return {
            "event_key": event_key,
            "ticker": row.get("ticker", ""),
            "company": row.get("company", ""),
            "event_date": row.get("event_date") or row.get("breach_date") or "",
            "event_category": row.get("event_category") or "cybersecurity",
            "event_subtype": row.get("event_subtype") or row.get("breach_type") or "",
            "distress_score": str(row.get("distress_score", "")).strip(),
            "distress_likelihood": str(row.get("distress_likelihood", "")).upper().strip(),
            "impact_score": str(row.get("impact_score", "")).strip(),
            "impact_likelihood": str(row.get("impact_likelihood", "")).upper().strip(),
            "impact_summary": (row.get("impact_summary") or "")[:500],
            "url": (row.get("url") or "").strip(),
            "title": (row.get("title") or "").strip(),
            "triage_engine": (row.get("triage_engine") or "deterministic").strip(),
            "validation_status": (row.get("validation_status") or "").strip().lower(),
            "validation_reason": (row.get("validation_reason") or "")[:500],
            "validation_confidence": str(row.get("validation_confidence", "")).strip(),
            "validation_engine": (row.get("validation_engine") or "").strip(),
            "alert_state": alert_state,
            "first_seen_at": row.get("first_seen_at") or now_iso,
            "last_seen_at": row.get("last_seen_at") or now_iso,
            "last_alerted_at": row.get("last_alerted_at") or "",
        }

    @staticmethod
    def build_event_key(
        ticker: str,
        event_date: str,
        event_category: str,
        source_url: str = "",
        title: str = "",
    ) -> str:
        import hashlib

        raw = "|".join(
            [
                (ticker or "").strip().upper(),
                (event_date or "").strip(),
                (event_category or "").strip().lower(),
                (source_url or "").strip().lower(),
                (title or "").strip().lower(),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]

    def upsert_triage_event(self, triage_event: Dict) -> Dict:
        """Insert/update triage row keyed by event_key and return normalized record."""
        record = self._normalize_triage_row(triage_event)
        fieldnames, rows = self._read_csv(self.triage_file)
        found = False
        for row in rows:
            if row.get("event_key") != record["event_key"]:
                continue
            found = True
            # Preserve state transitions unless caller explicitly requests a new state.
            incoming_state = (record.get("alert_state") or "").upper()
            existing_state = (row.get("alert_state") or "NEW").upper()
            keep_state = existing_state if incoming_state == "NEW" else incoming_state
            row.update(record)
            row["first_seen_at"] = row.get("first_seen_at") or record["first_seen_at"]
            row["last_seen_at"] = datetime.now().isoformat()
            row["alert_state"] = keep_state
            record = dict(row)
            break

        if not found:
            rows.append(record)

        self._write_csv(self.triage_file, fieldnames or self.TRIAGE_FIELDS, rows)
        return record

    def get_triage_events(
        self,
        alert_state: Optional[str] = None,
        min_impact_score: Optional[int] = None,
        min_distress_score: Optional[int] = None,
    ) -> List[Dict]:
        """Read triage rows with optional state/threshold filters."""
        _, rows = self._read_csv(self.triage_file)
        if not rows:
            return []
        out: List[Dict] = []
        target_state = (alert_state or "").upper().strip()
        for row in rows:
            if target_state and (row.get("alert_state", "").upper() != target_state):
                continue
            try:
                impact_score = int(str(row.get("impact_score", "0")).strip() or "0")
            except ValueError:
                impact_score = 0
            try:
                distress_score = int(str(row.get("distress_score", "0")).strip() or "0")
            except ValueError:
                distress_score = 0
            if min_impact_score is not None and impact_score < min_impact_score:
                continue
            if min_distress_score is not None and distress_score < min_distress_score:
                continue
            out.append(row)
        return out

    def mark_triage_sent(self, event_keys: List[str]) -> int:
        """Mark triage rows as SENT and stamp last_alerted_at."""
        if not event_keys:
            return 0
        key_set = {k.strip() for k in event_keys if k and k.strip()}
        if not key_set:
            return 0
        fieldnames, rows = self._read_csv(self.triage_file)
        if not rows:
            return 0
        now_iso = datetime.now().isoformat()
        updated = 0
        for row in rows:
            if row.get("event_key") not in key_set:
                continue
            row["alert_state"] = "SENT"
            row["last_alerted_at"] = now_iso
            row["last_seen_at"] = now_iso
            updated += 1
        if updated:
            self._write_csv(self.triage_file, fieldnames or self.TRIAGE_FIELDS, rows)
        return updated

    def mark_triage_state(self, event_key: str, state: str) -> bool:
        """Set triage state to one of NEW/SENT/ACKED/SUPPRESSED."""
        desired = (state or "").upper().strip()
        if desired not in ("NEW", "SENT", "ACKED", "SUPPRESSED"):
            return False
        fieldnames, rows = self._read_csv(self.triage_file)
        if not rows:
            return False
        updated = False
        for row in rows:
            if row.get("event_key") != event_key:
                continue
            row["alert_state"] = desired
            row["last_seen_at"] = datetime.now().isoformat()
            if desired == "SENT":
                row["last_alerted_at"] = datetime.now().isoformat()
            updated = True
            break
        if not updated:
            return False
        self._write_csv(self.triage_file, fieldnames or self.TRIAGE_FIELDS, rows)
        return True

    def add_event(self, event: Dict) -> bool:
        """Add a new event record using canonical event schema."""
        try:
            record = self._normalize_event_row(event)
            if self._event_exists(
                record.get("ticker", ""),
                record.get("event_date", ""),
                record.get("event_category", "cybersecurity"),
            ):
                return False

            with open(self.events_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.EVENTS_FIELDS)
                writer.writerow(record)
            return True
        except Exception as e:
            print(f"Error adding event: {e}")
            return False

    def add_breach(self, breach: Dict) -> bool:
        """Legacy alias for add_event."""
        return self.add_event(breach)

    def _event_exists(self, ticker: str, event_date: str, event_category: str) -> bool:
        if not os.path.exists(self.events_file):
            return False
        with open(self.events_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (
                    row.get("ticker") == ticker
                    and row.get("event_date") == event_date
                    and (row.get("event_category") or "cybersecurity") == (event_category or "cybersecurity")
                ):
                    return True
        return False

    def add_analysis(self, analysis: Dict) -> bool:
        try:
            with open(self.analysis_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.ANALYSIS_FIELDS)
                writer.writerow(self._normalize_analysis_row(analysis))
            return True
        except Exception as e:
            print(f"Error adding analysis: {e}")
            return False

    def add_signal(self, signal: Dict) -> bool:
        try:
            with open(self.signals_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.SIGNAL_FIELDS)
                writer.writerow(self._normalize_signal_row(signal))
            return True
        except Exception as e:
            print(f"Error adding signal: {e}")
            return False

    def _watch_exists(self, ticker: str, event_date: str, event_category: str) -> bool:
        if not os.path.exists(self.watchlist_file):
            return False
        with open(self.watchlist_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (
                    row.get("ticker") == ticker
                    and row.get("event_date") == event_date
                    and (row.get("event_category") or "cybersecurity") == (event_category or "cybersecurity")
                ):
                    return True
        return False

    def add_watch_if_new(self, watch: Dict) -> bool:
        """Add watchlist row if unique on (ticker, event_date, event_category)."""
        try:
            record = self._normalize_watch_row(watch)
            ticker = record.get("ticker", "")
            event_date = record.get("event_date", "")
            event_category = record.get("event_category", "cybersecurity")
            if not ticker or not event_date:
                return False
            if self._watch_exists(ticker, event_date, event_category):
                return False

            with open(self.watchlist_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.WATCHLIST_FIELDS)
                writer.writerow(record)
            return True
        except Exception as e:
            print(f"Error adding watch: {e}")
            return False

    def get_active_watches(self, max_days: int) -> List[Dict]:
        """Get active watch rows still within monitoring window."""
        results: List[Dict] = []
        if not os.path.exists(self.watchlist_file):
            return results

        now = datetime.now()
        with open(self.watchlist_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                status = (row.get("status") or "").upper()
                if status not in ("ACTIVE", "SIGNAL_CREATED"):
                    continue

                event_date = row.get("event_date", "")
                try:
                    event_dt = datetime.strptime(event_date, "%Y-%m-%d")
                except ValueError:
                    continue

                if (now - event_dt).days <= max_days:
                    row["status"] = status
                    # Backward compatibility until stream C threads event_date.
                    row["breach_date"] = row.get("event_date", "")
                    results.append(row)
        return results

    def mark_watch_last_checked(self, ticker: str, breach_date: str) -> bool:
        """Update last_checked_at for watch identified by legacy breach_date arg."""
        return self._update_watch_row(
            ticker=ticker,
            event_date=breach_date,
            updater=lambda row: row.update({"last_checked_at": datetime.now().isoformat()}),
        )

    def mark_watch_signal_created(self, ticker: str, breach_date: str) -> bool:
        return self._mark_watch_status(ticker, breach_date, "SIGNAL_CREATED")

    def update_watch_metadata(
        self,
        ticker: str,
        breach_date: str,
        company: Optional[str] = None,
        source: Optional[str] = None,
        url: Optional[str] = None,
    ) -> bool:
        def _update(row: Dict) -> None:
            if company is not None:
                row["company"] = company
            if source is not None:
                row["source"] = source
            if url is not None:
                row["url"] = url

        return self._update_watch_row(ticker=ticker, event_date=breach_date, updater=_update)

    def mark_watch_expired(self, ticker: str, breach_date: str) -> bool:
        return self._mark_watch_status(ticker, breach_date, "EXPIRED")

    def _mark_watch_status(self, ticker: str, breach_date: str, status: str) -> bool:
        return self._update_watch_row(
            ticker=ticker,
            event_date=breach_date,
            updater=lambda row: row.update({"status": status}),
        )

    def _update_watch_row(self, ticker: str, event_date: str, updater) -> bool:
        try:
            fieldnames, rows = self._read_csv(self.watchlist_file)
            if not rows:
                return False

            updated = False
            for row in rows:
                if row.get("ticker") == ticker and row.get("event_date") == event_date:
                    updater(row)
                    updated = True

            if not updated:
                return False

            self._write_csv(self.watchlist_file, fieldnames or self.WATCHLIST_FIELDS, rows)
            return True
        except Exception as e:
            print(f"Error updating watch row: {e}")
            return False

    def _timeseries_exists(self, ticker: str, event_date: str, event_category: str) -> bool:
        if not os.path.exists(self.timeseries_file):
            return False
        with open(self.timeseries_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if (
                    row.get("ticker") == ticker
                    and row.get("event_date") == event_date
                    and (row.get("event_category") or "cybersecurity") == (event_category or "cybersecurity")
                ):
                    return True
        return False

    def mark_timeseries_saved(self, ticker: str, breach_date: str) -> bool:
        return self._update_watch_row(
            ticker=ticker,
            event_date=breach_date,
            updater=lambda row: row.update({"timeseries_saved": "Yes"}),
        )

    def add_price_timeseries(self, rows: List[Dict]) -> bool:
        """Append event timeseries rows if that event does not already exist."""
        try:
            if not rows:
                return False

            normalized_rows = [self._normalize_timeseries_row(r) for r in rows]
            first = normalized_rows[0]
            ticker = first.get("ticker", "")
            event_date = first.get("event_date", "")
            event_category = first.get("event_category", "cybersecurity")
            if not ticker or not event_date:
                return False
            if self._timeseries_exists(ticker, event_date, event_category):
                return False

            with open(self.timeseries_file, "a", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=self.TIMESERIES_FIELDS)
                writer.writerows(normalized_rows)
            return True
        except Exception as e:
            print(f"Error adding price timeseries: {e}")
            return False

    def get_events(self, ticker: str = None, event_category: str = None) -> List[Dict]:
        results: List[Dict] = []
        if not os.path.exists(self.events_file):
            return results
        with open(self.events_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker and row.get("ticker") != ticker:
                    continue
                if event_category and row.get("event_category") != event_category:
                    continue
                results.append(row)
        return results

    def get_breaches(self, ticker: str = None) -> List[Dict]:
        """
        Legacy compatibility method.

        Returns canonical rows with breach_* aliases included for callers not yet migrated.
        """
        events = self.get_events(ticker=ticker)
        results: List[Dict] = []
        for event in events:
            enriched = dict(event)
            enriched["date_found"] = event.get("event_date", "")
            enriched["breach_date"] = event.get("event_date", "")
            enriched["breach_type"] = event.get("event_subtype", "")
            results.append(enriched)
        return results

    def get_analysis_history(self, ticker: str = None) -> List[Dict]:
        results: List[Dict] = []
        if not os.path.exists(self.analysis_file):
            return results

        with open(self.analysis_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker and row.get("ticker") != ticker:
                    continue
                # Legacy aliases for stream-C transition.
                row["breach_date"] = row.get("event_date", "")
                row["pre_breach_price"] = row.get("pre_event_price", "")
                row["min_price_post_breach"] = row.get("min_price_post_event", "")
                row["volume_spike_at_breach"] = row.get("volume_spike_at_event", "")
                results.append(row)
        return results

    def get_signals(self, ticker: str = None, executed_only: bool = False) -> List[Dict]:
        results: List[Dict] = []
        if not os.path.exists(self.signals_file):
            return results

        with open(self.signals_file, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if ticker and row.get("ticker") != ticker:
                    continue
                if executed_only and row.get("executed") != "Yes":
                    continue
                row["breach_date"] = row.get("event_date", "")
                results.append(row)
        return results

    def update_signal_execution(
        self, ticker: str, execution_price: float, execution_date: str = None
    ) -> bool:
        if not execution_date:
            execution_date = datetime.now().strftime("%Y-%m-%d")

        fieldnames, signals = self._read_csv(self.signals_file)
        if not signals:
            return False

        for row in signals:
            if row.get("ticker") == ticker and row.get("executed") != "Yes":
                row["executed"] = "Yes"
                row["execution_price"] = execution_price
                row["execution_date"] = execution_date

        try:
            self._write_csv(self.signals_file, fieldnames or self.SIGNAL_FIELDS, signals)
            return True
        except Exception as e:
            print(f"Error updating signal: {e}")
            return False

    def get_statistics(self) -> Dict:
        events = self.get_events()
        signals = self.get_signals()
        executed_signals = [s for s in signals if s.get("executed") == "Yes"]
        signal_tickers = set(s.get("ticker") for s in signals)
        winning_signals = len(
            [s for s in executed_signals if s.get("outcome", "").lower() == "win"]
        )
        win_rate = (winning_signals / len(executed_signals) * 100) if executed_signals else 0

        return {
            "total_events": len(events),
            "total_breaches": len(events),  # Legacy key
            "total_signals": len(signals),
            "executed_signals": len(executed_signals),
            "unexecuted_signals": len(signals) - len(executed_signals),
            "signals_win_rate": f"{win_rate:.1f}%",
            "unique_tickers_in_signals": len(signal_tickers),
            "events_by_source": self._count_by_field(events, "source"),
            "breaches_by_source": self._count_by_field(events, "source"),  # Legacy key
            "signals_by_confidence": self._count_by_field(signals, "confidence_level"),
        }

    @staticmethod
    def _parse_ymd(value: str) -> Optional[datetime]:
        try:
            return datetime.strptime((value or "").strip(), "%Y-%m-%d")
        except ValueError:
            return None

    @staticmethod
    def _pct(numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return round((numerator / denominator) * 100.0, 1)

    def get_category_yield_dashboard(
        self,
        days: int = 30,
        categories: Optional[List[str]] = None,
    ) -> Dict:
        """
        Return per-category yield funnel metrics for a lookback window.

        Funnel tracked:
          events -> watches -> analyses -> signals
        """
        lookback_days = max(1, int(days))
        cutoff = datetime.now() - timedelta(days=lookback_days)

        events = self.get_events()
        analyses = self.get_analysis_history()
        signals = self.get_signals()

        _, watch_rows = self._read_csv(self.watchlist_file)
        if categories:
            category_list = [c for c in categories if c]
        else:
            discovered = set()
            for row in events:
                discovered.add((row.get("event_category") or "cybersecurity").strip())
            for row in watch_rows:
                discovered.add((row.get("event_category") or "cybersecurity").strip())
            for row in analyses:
                discovered.add((row.get("event_category") or "cybersecurity").strip())
            for row in signals:
                discovered.add((row.get("event_category") or "cybersecurity").strip())
            category_list = sorted(c for c in discovered if c)

        # Windowed slices by event_date so steps stay comparable.
        events_w = []
        for row in events:
            dt = self._parse_ymd(row.get("event_date", ""))
            if dt and dt >= cutoff:
                events_w.append(row)

        watches_w = []
        for row in watch_rows:
            dt = self._parse_ymd(row.get("event_date", ""))
            if dt and dt >= cutoff:
                watches_w.append(row)

        analyses_w = []
        for row in analyses:
            dt = self._parse_ymd(row.get("event_date", ""))
            if dt and dt >= cutoff:
                analyses_w.append(row)

        signals_w = []
        for row in signals:
            dt = self._parse_ymd(row.get("event_date", ""))
            if dt and dt >= cutoff:
                signals_w.append(row)

        def _funnel_key(row: Dict) -> Tuple[str, str, str]:
            return (
                (row.get("ticker") or "").strip(),
                (row.get("event_date") or "").strip(),
                ((row.get("event_category") or "cybersecurity").strip()),
            )

        rows: List[Dict] = []
        totals = {
            "events": 0,
            "watches": 0,
            "analyses": 0,
            "signals": 0,
            "unique_event_tickers": 0,
            "unique_signal_tickers": 0,
            "_event_to_watch_numerator": 0,
            "_watch_to_analysis_numerator": 0,
            "_analysis_to_signal_numerator": 0,
            "_event_to_signal_numerator": 0,
        }
        total_event_tickers: set = set()
        total_signal_tickers: set = set()

        for category in category_list:
            c_events = [r for r in events_w if (r.get("event_category") or "cybersecurity") == category]
            c_watches = [r for r in watches_w if (r.get("event_category") or "cybersecurity") == category]
            c_analyses = [r for r in analyses_w if (r.get("event_category") or "cybersecurity") == category]
            c_signals = [r for r in signals_w if (r.get("event_category") or "cybersecurity") == category]
            event_keys = {_funnel_key(r) for r in c_events if _funnel_key(r)[0] and _funnel_key(r)[1]}
            watch_keys = {_funnel_key(r) for r in c_watches if _funnel_key(r)[0] and _funnel_key(r)[1]}
            analysis_keys = {_funnel_key(r) for r in c_analyses if _funnel_key(r)[0] and _funnel_key(r)[1]}
            signal_keys = {_funnel_key(r) for r in c_signals if _funnel_key(r)[0] and _funnel_key(r)[1]}
            watch_from_events = watch_keys.intersection(event_keys)
            analysis_from_watch = analysis_keys.intersection(watch_keys)
            signal_from_analysis = signal_keys.intersection(analysis_keys)
            signal_from_events = signal_keys.intersection(event_keys)

            active_watches = 0
            signal_created_watches = 0
            expired_watches = 0
            for r in c_watches:
                status = (r.get("status") or "").upper()
                if status == "ACTIVE":
                    active_watches += 1
                elif status == "SIGNAL_CREATED":
                    signal_created_watches += 1
                elif status == "EXPIRED":
                    expired_watches += 1

            event_tickers = {r.get("ticker", "") for r in c_events if r.get("ticker", "")}
            signal_tickers = {r.get("ticker", "") for r in c_signals if r.get("ticker", "")}
            total_event_tickers.update(event_tickers)
            total_signal_tickers.update(signal_tickers)

            metrics = {
                "event_category": category,
                "events": len(event_keys),
                "unique_event_tickers": len(event_tickers),
                "watches": len(watch_keys),
                "active_watches": active_watches,
                "signal_created_watches": signal_created_watches,
                "expired_watches": expired_watches,
                "analyses": len(analysis_keys),
                "signals": len(signal_keys),
                "unique_signal_tickers": len(signal_tickers),
                "event_to_watch_rate_pct": self._pct(len(watch_from_events), len(event_keys)),
                "watch_to_analysis_rate_pct": self._pct(len(analysis_from_watch), len(watch_keys)),
                "analysis_to_signal_rate_pct": self._pct(len(signal_from_analysis), len(analysis_keys)),
                "event_to_signal_rate_pct": self._pct(len(signal_from_events), len(event_keys)),
                "raw_events": len(c_events),
                "raw_watches": len(c_watches),
                "raw_analyses": len(c_analyses),
                "raw_signals": len(c_signals),
            }
            rows.append(metrics)

            totals["events"] += metrics["events"]
            totals["watches"] += metrics["watches"]
            totals["analyses"] += metrics["analyses"]
            totals["signals"] += metrics["signals"]
            totals["_event_to_watch_numerator"] += len(watch_from_events)
            totals["_watch_to_analysis_numerator"] += len(analysis_from_watch)
            totals["_analysis_to_signal_numerator"] += len(signal_from_analysis)
            totals["_event_to_signal_numerator"] += len(signal_from_events)

        totals["unique_event_tickers"] = len(total_event_tickers)
        totals["unique_signal_tickers"] = len(total_signal_tickers)
        totals["event_to_watch_rate_pct"] = self._pct(totals["_event_to_watch_numerator"], totals["events"])
        totals["watch_to_analysis_rate_pct"] = self._pct(totals["_watch_to_analysis_numerator"], totals["watches"])
        totals["analysis_to_signal_rate_pct"] = self._pct(totals["_analysis_to_signal_numerator"], totals["analyses"])
        totals["event_to_signal_rate_pct"] = self._pct(totals["_event_to_signal_numerator"], totals["events"])
        totals.pop("_event_to_watch_numerator", None)
        totals.pop("_watch_to_analysis_numerator", None)
        totals.pop("_analysis_to_signal_numerator", None)
        totals.pop("_event_to_signal_numerator", None)

        return {
            "window_days": lookback_days,
            "as_of": datetime.now().isoformat(),
            "rows": rows,
            "totals": totals,
        }

    def display_category_yield_dashboard(
        self,
        days: int = 30,
        categories: Optional[List[str]] = None,
    ) -> None:
        dashboard = self.get_category_yield_dashboard(days=days, categories=categories)
        rows = dashboard.get("rows", [])
        totals = dashboard.get("totals", {})

        print("\nCATEGORY YIELD DASHBOARD")
        print("=" * 100)
        print(f"Window: last {dashboard.get('window_days', days)} days")
        print("Counts are unique by (ticker, event_date, event_category).")
        print("Conversion rates use stage-overlap keys for stable funnel math.")

        if not rows:
            print("No category data available in the selected window.")
            return

        print(
            f"{'Category':<30} {'Events':>7} {'Watches':>8} {'Analyses':>9} {'Signals':>8} "
            f"{'E->W%':>7} {'W->A%':>7} {'A->S%':>7} {'E->S%':>7}"
        )
        print("-" * 100)
        for row in rows:
            print(
                f"{row.get('event_category', ''):<30} "
                f"{row.get('events', 0):>7} "
                f"{row.get('watches', 0):>8} "
                f"{row.get('analyses', 0):>9} "
                f"{row.get('signals', 0):>8} "
                f"{row.get('event_to_watch_rate_pct', 0.0):>7.1f} "
                f"{row.get('watch_to_analysis_rate_pct', 0.0):>7.1f} "
                f"{row.get('analysis_to_signal_rate_pct', 0.0):>7.1f} "
                f"{row.get('event_to_signal_rate_pct', 0.0):>7.1f}"
            )

        print("-" * 100)
        print(
            f"{'TOTAL':<30} "
            f"{totals.get('events', 0):>7} "
            f"{totals.get('watches', 0):>8} "
            f"{totals.get('analyses', 0):>9} "
            f"{totals.get('signals', 0):>8} "
            f"{totals.get('event_to_watch_rate_pct', 0.0):>7.1f} "
            f"{totals.get('watch_to_analysis_rate_pct', 0.0):>7.1f} "
            f"{totals.get('analysis_to_signal_rate_pct', 0.0):>7.1f} "
            f"{totals.get('event_to_signal_rate_pct', 0.0):>7.1f}"
        )

    def _count_by_field(self, records: List[Dict], field: str) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for record in records:
            value = record.get(field, "Unknown")
            counts[value] = counts.get(value, 0) + 1
        return counts

    def display_statistics(self) -> None:
        stats = self.get_statistics()
        print("\nDATABASE STATISTICS")
        print("=" * 60)
        print(f"Total events recorded:    {stats['total_events']}")
        print(f"Total signals generated:  {stats['total_signals']}")
        print(f"  - Executed:             {stats['executed_signals']}")
        print(f"  - Pending:              {stats['unexecuted_signals']}")
        print(f"Signals win rate:         {stats['signals_win_rate']}")
        print(f"Unique tickers:           {stats['unique_tickers_in_signals']}")

        if stats["events_by_source"]:
            print("\nEvents by source:")
            for source, count in stats["events_by_source"].items():
                print(f"  {source}: {count}")

        if stats["signals_by_confidence"]:
            print("\nSignals by confidence:")
            for conf, count in stats["signals_by_confidence"].items():
                print(f"  {conf}: {count}")

    def export_to_json(self, filename: str = "event_analysis.json") -> bool:
        try:
            data = {
                "events": self.get_events(),
                "analysis": self.get_analysis_history(),
                "signals": self.get_signals(),
                "statistics": self.get_statistics(),
                "exported": datetime.now().isoformat(),
            }

            with open(filename, "w") as f:
                json.dump(data, f, indent=2)
            print(f"Data exported to {filename}")
            return True
        except Exception as e:
            print(f"Error exporting data: {e}")
            return False


def main():
    """Minimal database manager smoke example."""
    db = DatabaseManager()
    sample_event = {
        "company": "Acme Corp",
        "ticker": "ACME",
        "event_date": "2024-01-15",
        "event_category": "cybersecurity",
        "event_subtype": "Data Exfiltration",
        "severity": "High",
        "source": "BleepingComputer",
        "url": "https://example.com/event",
        "summary": "Major event affecting 100,000 users",
    }
    sample_analysis = {
        "ticker": "ACME",
        "event_date": "2024-01-15",
        "event_category": "cybersecurity",
        "pre_event_price": 50.0,
        "current_price": 42.0,
        "min_price_post_event": 40.0,
        "max_drop_pct": 20.0,
        "recovery_days": None,
        "current_rsi": 28.5,
        "volume_spike_at_event": 2.3,
    }

    db.add_event(sample_event)
    db.add_analysis(sample_analysis)
    db.display_statistics()


if __name__ == "__main__":
    main()
