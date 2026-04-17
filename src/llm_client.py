"""
Centralized LLM client with cost control.

All enrichers that use paid LLMs (impact triage agent path, narrative clustering,
materiality extraction, subtype normalizer, signal freshness guardrail, entity
agent validation) must go through this client so that budgets, the content-hash
cache, the accounting ledger, and the circuit breaker apply uniformly.

Design goals (from the plan):
1. Cascade: deterministic > cached verdict > local model > paid LLM.
2. Hard budgets: per-call token caps, per-cycle call count, daily/monthly USD caps,
   per-category daily caps, and a minimum distress-score threshold before any call.
3. Accounting ledger: every call (used / cached / skipped / error) persists to
   data/llm_usage.csv so overages can be audited and daily/monthly totals can be
   computed without relying on provider dashboards.
4. Deterministic fallback: callers always receive a valid LLMResult. If budget is
   exhausted or the provider fails, `result.used_llm == False` and the caller is
   expected to use its deterministic path.
5. Dry-run: `llm_budget.dry_run=true` never hits the network; it only logs what a
   real call would have cost. This is the default shipping posture.

This module has no hard dependency on `requests`; it degrades gracefully when the
library is missing. Providers are pluggable via the existing environment-variable
conventions used by `impact_triage.py` and `entity_extractor.py`.
"""

from __future__ import annotations

import csv
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

try:  # pragma: no cover - requests is a project dep
    import requests
except ImportError:  # pragma: no cover
    requests = None


LEDGER_COLUMNS = [
    "ts_utc",
    "cycle_id",
    "module",
    "provider",
    "model",
    "input_tokens",
    "output_tokens",
    "est_cost_usd",
    "decision",
    "content_hash",
    "event_category",
]


# Decision taxonomy used in the ledger and returned to callers.
DECISION_DETERMINISTIC = "deterministic"
DECISION_CACHE_HIT = "cached"
DECISION_USED = "used"
DECISION_DRY_RUN = "dry_run"
DECISION_SKIP_DISABLED = "skipped_disabled"
DECISION_SKIP_CAP_CALLS = "skipped_per_cycle_cap"
DECISION_SKIP_CAP_CATEGORY = "skipped_category_cap"
DECISION_SKIP_CAP_DAILY = "skipped_daily_cap"
DECISION_SKIP_CAP_MONTHLY = "skipped_monthly_cap"
DECISION_SKIP_DISTRESS = "skipped_low_distress"
DECISION_SKIP_INPUT_TOO_LARGE = "skipped_input_too_large"
DECISION_SKIP_CIRCUIT_OPEN = "skipped_circuit_open"
DECISION_ERROR = "error"


@dataclass
class LLMResult:
    """
    Return envelope for every call. Callers must always handle the case where
    `used_llm` is False and fall back to their deterministic logic.
    """

    used_llm: bool
    data: Dict[str, Any] = field(default_factory=dict)
    decision: str = DECISION_DETERMINISTIC
    provider: str = ""
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    content_hash: str = ""
    reason: str = ""


def _estimate_tokens(text: str) -> int:
    """Crude pre-request token estimate. Real usage is replaced post-call from provider data."""
    if not text:
        return 0
    return max(1, int(len(text) / 4))


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _month_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _compute_content_hash(payload: Dict[str, Any]) -> str:
    try:
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        canonical = str(payload)
    return hashlib.sha256(canonical.encode("utf-8", errors="replace")).hexdigest()


def _resolve_rel_path(relative_path: str) -> str:
    if os.path.isabs(relative_path):
        return relative_path
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(base_dir, relative_path))


class _ContentHashCache:
    """JSON-backed cache keyed by content_hash with TTL."""

    def __init__(self, path: str, ttl_days: int):
        self.path = path
        self.ttl_seconds = max(0, int(ttl_days)) * 86400
        self._lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict):
                self._data = raw
        except (OSError, json.JSONDecodeError):
            self._data = {}

    def _save(self) -> None:
        if not self.path:
            return
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            # cache is a performance optimization; never raise from cache writes
            pass

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        if not key:
            return None
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            if self.ttl_seconds > 0:
                ts = float(entry.get("stored_at_ts", 0.0) or 0.0)
                if ts and time.time() - ts > self.ttl_seconds:
                    self._data.pop(key, None)
                    self._save()
                    return None
            payload = entry.get("payload")
            return payload if isinstance(payload, dict) else None

    def put(self, key: str, payload: Dict[str, Any]) -> None:
        if not key:
            return
        with self._lock:
            self._data[key] = {
                "stored_at_ts": time.time(),
                "payload": payload,
            }
            self._save()


class _UsageLedger:
    """Append-only CSV ledger + running daily/monthly totals."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._lock = threading.Lock()
        self._daily_usd: Dict[str, float] = {}
        self._monthly_usd: Dict[str, float] = {}
        self._daily_calls_by_category: Dict[Tuple[str, str], int] = {}
        self._load_totals()

    def _load_totals(self) -> None:
        if not self.csv_path or not os.path.exists(self.csv_path):
            return
        try:
            with open(self.csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    decision = row.get("decision", "")
                    cost = float(row.get("est_cost_usd") or 0.0)
                    ts = row.get("ts_utc", "")
                    category = row.get("event_category", "")
                    day = ts[:10] if ts else ""
                    month = ts[:7] if ts else ""
                    if decision in (DECISION_USED, DECISION_DRY_RUN, DECISION_CACHE_HIT):
                        if day:
                            self._daily_usd[day] = self._daily_usd.get(day, 0.0) + cost
                        if month:
                            self._monthly_usd[month] = self._monthly_usd.get(month, 0.0) + cost
                    if decision == DECISION_USED and day:
                        key = (day, category)
                        self._daily_calls_by_category[key] = (
                            self._daily_calls_by_category.get(key, 0) + 1
                        )
        except (OSError, ValueError):
            pass

    def append(self, row: Dict[str, Any]) -> None:
        if not self.csv_path:
            return
        with self._lock:
            new_file = not os.path.exists(self.csv_path)
            try:
                os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
                with open(self.csv_path, "a", encoding="utf-8", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=LEDGER_COLUMNS)
                    if new_file:
                        writer.writeheader()
                    writer.writerow({col: row.get(col, "") for col in LEDGER_COLUMNS})
            except OSError:
                # Ledger writes are best-effort; refusing to record a call should
                # never block the pipeline.
                pass

            decision = row.get("decision", "")
            cost = float(row.get("est_cost_usd") or 0.0)
            day = _today_key()
            month = _month_key()
            if decision in (DECISION_USED, DECISION_DRY_RUN, DECISION_CACHE_HIT):
                self._daily_usd[day] = self._daily_usd.get(day, 0.0) + cost
                self._monthly_usd[month] = self._monthly_usd.get(month, 0.0) + cost
            if decision == DECISION_USED:
                key = (day, str(row.get("event_category", "")))
                self._daily_calls_by_category[key] = (
                    self._daily_calls_by_category.get(key, 0) + 1
                )

    def daily_spend(self) -> float:
        return float(self._daily_usd.get(_today_key(), 0.0))

    def monthly_spend(self) -> float:
        return float(self._monthly_usd.get(_month_key(), 0.0))

    def daily_category_calls(self, category: str) -> int:
        return int(self._daily_calls_by_category.get((_today_key(), str(category)), 0))


class LLMClient:
    """Cost-controlled, cascade-aware LLM wrapper."""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        self.settings = settings or {}
        cfg = self.settings.get("llm_budget", {}) or {}

        self.enabled = bool(cfg.get("enabled", True))
        self.dry_run = bool(cfg.get("dry_run", True))

        self.per_call_max_input_tokens = int(cfg.get("per_call_max_input_tokens", 4000))
        self.per_call_max_output_tokens = int(cfg.get("per_call_max_output_tokens", 800))
        self.per_cycle_max_calls = int(cfg.get("per_cycle_max_calls", 5))
        self.daily_usd_cap = float(cfg.get("daily_usd_cap", 0.0))
        self.monthly_usd_cap = float(cfg.get("monthly_usd_cap", 0.0))
        self.per_category_daily_max_calls = int(cfg.get("per_category_daily_max_calls", 0))
        self.min_distress_score_for_llm = int(cfg.get("min_distress_score_for_llm", 40))
        self.alert_threshold_pct_of_cap = float(cfg.get("alert_threshold_pct_of_cap", 80.0))
        self.circuit_breaker_cooldown_seconds = int(
            cfg.get("circuit_breaker_cooldown_seconds", 600)
        )

        providers_cfg = cfg.get("providers", {}) or {}
        self.providers_cfg = providers_cfg if isinstance(providers_cfg, dict) else {}

        cache_file = cfg.get("cache_file", "../data/llm_call_cache.json")
        cache_ttl_days = int(cfg.get("cache_ttl_days", 30))
        ledger_csv = cfg.get("ledger_csv", "../data/llm_usage.csv")

        self.cache = _ContentHashCache(_resolve_rel_path(cache_file), cache_ttl_days)
        self.ledger = _UsageLedger(_resolve_rel_path(ledger_csv))

        self._cycle_calls = 0
        self._circuit_open_until: float = 0.0
        self._cycle_id: str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ---- public lifecycle hooks ----

    def start_cycle(self, cycle_id: Optional[str] = None) -> None:
        """Reset per-cycle counters. Call at the top of each monitor cycle."""
        self._cycle_calls = 0
        self._cycle_id = cycle_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # ---- cost helpers ----

    def _cost_for(self, provider: str, input_tokens: int, output_tokens: int) -> float:
        prov = self.providers_cfg.get(provider, {}) if isinstance(self.providers_cfg, dict) else {}
        try:
            input_per_1k = float(prov.get("input_usd_per_1k", 0.0) or 0.0)
            output_per_1k = float(prov.get("output_usd_per_1k", 0.0) or 0.0)
        except (TypeError, ValueError):
            input_per_1k = 0.0
            output_per_1k = 0.0
        return (input_tokens / 1000.0) * input_per_1k + (output_tokens / 1000.0) * output_per_1k

    # ---- budget gating ----

    def _gate_decision(
        self,
        module: str,
        event_category: str,
        distress_score: int,
        estimated_input_tokens: int,
    ) -> Optional[str]:
        """
        Evaluate hard budget gates. Returns a DECISION_SKIP_* code if the call must be
        suppressed, or None if the call is allowed. Caller logs the ledger row.
        """
        if not self.enabled:
            return DECISION_SKIP_DISABLED

        if self._circuit_open_until and time.time() < self._circuit_open_until:
            return DECISION_SKIP_CIRCUIT_OPEN

        # Skip low-impact articles to protect budget.
        if (
            self.min_distress_score_for_llm > 0
            and distress_score is not None
            and int(distress_score) < self.min_distress_score_for_llm
        ):
            return DECISION_SKIP_DISTRESS

        if (
            self.per_cycle_max_calls > 0
            and self._cycle_calls >= self.per_cycle_max_calls
        ):
            return DECISION_SKIP_CAP_CALLS

        if self.per_category_daily_max_calls > 0 and event_category:
            used = self.ledger.daily_category_calls(event_category)
            if used >= self.per_category_daily_max_calls:
                return DECISION_SKIP_CAP_CATEGORY

        if estimated_input_tokens > self.per_call_max_input_tokens:
            return DECISION_SKIP_INPUT_TOO_LARGE

        if self.daily_usd_cap > 0.0 and self.ledger.daily_spend() >= self.daily_usd_cap:
            return DECISION_SKIP_CAP_DAILY

        if self.monthly_usd_cap > 0.0 and self.ledger.monthly_spend() >= self.monthly_usd_cap:
            return DECISION_SKIP_CAP_MONTHLY

        return None

    # ---- circuit breaker ----

    def _open_circuit(self) -> None:
        self._circuit_open_until = time.time() + max(0, self.circuit_breaker_cooldown_seconds)

    # ---- main entrypoint ----

    def call(
        self,
        module: str,
        prompt_key: str,
        prompt_payload: Dict[str, Any],
        event_category: str = "",
        distress_score: int = 0,
        provider: str = "generic_http",
        model: str = "",
        call_fn: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None,
    ) -> LLMResult:
        """
        Run the cascade for a single enrichment.

        Parameters
        ----------
        module
            Short identifier used in the ledger and cache namespace.
        prompt_key
            Stable identifier for the prompt shape (e.g. 'materiality_v1'). Included
            in the content hash so prompt migrations don't reuse old cached answers.
        prompt_payload
            The payload an LLM would consume. Hashed verbatim after normalization.
        event_category
            Used for per-category daily caps and ledger annotation.
        distress_score
            Used to gate calls on low-impact articles.
        provider, model
            Cost lookup keys; also persisted to the ledger.
        call_fn
            Optional callable that performs the actual network call. It must accept
            the payload dict and return a dict that may include the following keys:
            - 'data' (any JSON-serializable payload to return to the caller)
            - 'input_tokens', 'output_tokens' (observed usage, when provider reports)

        Returns
        -------
        LLMResult
            `used_llm=True` means the caller may use `result.data`; otherwise the
            caller must fall back to its deterministic output.
        """
        content_hash = _compute_content_hash({"prompt_key": prompt_key, "payload": prompt_payload})

        # Step 1: cache hit (cheapest non-deterministic layer).
        cached = self.cache.get(content_hash)
        if cached is not None:
            cached_provider = str(cached.get("provider", provider))
            cached_model = str(cached.get("model", model))
            cost = float(cached.get("cost_usd", 0.0))
            result = LLMResult(
                used_llm=True,
                data=cached.get("data", {}) if isinstance(cached.get("data"), dict) else {},
                decision=DECISION_CACHE_HIT,
                provider=cached_provider,
                model=cached_model,
                input_tokens=int(cached.get("input_tokens", 0) or 0),
                output_tokens=int(cached.get("output_tokens", 0) or 0),
                cost_usd=0.0,  # cache hits don't re-spend
                content_hash=content_hash,
                reason="cache_hit",
            )
            self._log_ledger(module, result, event_category, cost_override=0.0)
            return result

        # Step 2: budget gates.
        estimated_input_tokens = _estimate_tokens(json.dumps(prompt_payload, default=str))
        estimated_cost = self._cost_for(
            provider, estimated_input_tokens, self.per_call_max_output_tokens
        )
        skip_reason = self._gate_decision(
            module=module,
            event_category=event_category,
            distress_score=distress_score,
            estimated_input_tokens=estimated_input_tokens,
        )
        if skip_reason:
            result = LLMResult(
                used_llm=False,
                decision=skip_reason,
                provider=provider,
                model=model,
                input_tokens=estimated_input_tokens,
                output_tokens=0,
                cost_usd=0.0,
                content_hash=content_hash,
                reason=skip_reason,
            )
            self._log_ledger(module, result, event_category)
            return result

        # Step 3: dry-run path (default shipping posture).
        if self.dry_run:
            result = LLMResult(
                used_llm=False,
                decision=DECISION_DRY_RUN,
                provider=provider,
                model=model,
                input_tokens=estimated_input_tokens,
                output_tokens=self.per_call_max_output_tokens,
                cost_usd=estimated_cost,
                content_hash=content_hash,
                reason="dry_run_disabled_network",
            )
            self._log_ledger(module, result, event_category)
            self._cycle_calls += 1
            self._maybe_alert_on_cap()
            return result

        # Step 4: live call (only when enabled, dry_run=false, and call_fn provided).
        if call_fn is None or requests is None:
            result = LLMResult(
                used_llm=False,
                decision=DECISION_SKIP_DISABLED,
                provider=provider,
                model=model,
                input_tokens=estimated_input_tokens,
                output_tokens=0,
                cost_usd=0.0,
                content_hash=content_hash,
                reason="no_live_call_fn_or_requests",
            )
            self._log_ledger(module, result, event_category)
            return result

        try:
            response = call_fn(prompt_payload) or {}
        except Exception as exc:  # pragma: no cover - network path
            self._open_circuit()
            result = LLMResult(
                used_llm=False,
                decision=DECISION_ERROR,
                provider=provider,
                model=model,
                input_tokens=estimated_input_tokens,
                output_tokens=0,
                cost_usd=0.0,
                content_hash=content_hash,
                reason=f"exception:{type(exc).__name__}",
            )
            self._log_ledger(module, result, event_category)
            return result

        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        input_tokens = int(response.get("input_tokens", estimated_input_tokens) or estimated_input_tokens)
        output_tokens = int(response.get("output_tokens", 0) or 0)
        cost = self._cost_for(provider, input_tokens, output_tokens)

        result = LLMResult(
            used_llm=True,
            data=data,
            decision=DECISION_USED,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            content_hash=content_hash,
            reason="live_call",
        )
        self.cache.put(
            content_hash,
            {
                "data": data,
                "provider": provider,
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost,
            },
        )
        self._log_ledger(module, result, event_category)
        self._cycle_calls += 1
        self._maybe_alert_on_cap()
        return result

    # ---- ledger glue ----

    def _log_ledger(
        self,
        module: str,
        result: LLMResult,
        event_category: str,
        cost_override: Optional[float] = None,
    ) -> None:
        cost = cost_override if cost_override is not None else result.cost_usd
        self.ledger.append(
            {
                "ts_utc": datetime.now(timezone.utc).isoformat(),
                "cycle_id": self._cycle_id,
                "module": module,
                "provider": result.provider,
                "model": result.model,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "est_cost_usd": f"{float(cost):.6f}",
                "decision": result.decision,
                "content_hash": result.content_hash,
                "event_category": event_category,
            }
        )

    def _maybe_alert_on_cap(self) -> None:
        """
        Lightweight stderr signal when we cross the alert threshold on either cap.
        Alert channels (ntfy/email) plug in at a higher layer; we keep this class
        free of alerting imports to avoid circular dependencies.
        """
        if self.daily_usd_cap > 0:
            pct = self.ledger.daily_spend() / self.daily_usd_cap * 100.0
            if pct >= self.alert_threshold_pct_of_cap:
                print(
                    f"[llm_client] WARNING daily LLM spend at "
                    f"{pct:.1f}% of ${self.daily_usd_cap:.2f} cap"
                )
        if self.monthly_usd_cap > 0:
            pct = self.ledger.monthly_spend() / self.monthly_usd_cap * 100.0
            if pct >= self.alert_threshold_pct_of_cap:
                print(
                    f"[llm_client] WARNING monthly LLM spend at "
                    f"{pct:.1f}% of ${self.monthly_usd_cap:.2f} cap"
                )

    # ---- observability / introspection ----

    def snapshot_usage(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot of current spend + cycle counters."""
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "cycle_id": self._cycle_id,
            "cycle_calls": self._cycle_calls,
            "daily_spend_usd": round(self.ledger.daily_spend(), 6),
            "monthly_spend_usd": round(self.ledger.monthly_spend(), 6),
            "daily_usd_cap": self.daily_usd_cap,
            "monthly_usd_cap": self.monthly_usd_cap,
            "per_cycle_max_calls": self.per_cycle_max_calls,
            "circuit_open_until_ts": self._circuit_open_until,
        }


_singleton: Optional[LLMClient] = None
_singleton_lock = threading.Lock()


def get_llm_client(settings: Optional[Dict[str, Any]] = None) -> LLMClient:
    """
    Return a process-wide LLMClient. The first call's settings are used; subsequent
    calls that pass settings will re-initialize the client. This matches how other
    modules in this repo accept either a settings dict or fall back to a loader.
    """
    global _singleton
    with _singleton_lock:
        if _singleton is None or settings is not None:
            _singleton = LLMClient(settings or {})
        return _singleton


__all__ = [
    "LLMClient",
    "LLMResult",
    "get_llm_client",
    "DECISION_USED",
    "DECISION_CACHE_HIT",
    "DECISION_DRY_RUN",
    "DECISION_DETERMINISTIC",
    "DECISION_SKIP_CAP_CALLS",
    "DECISION_SKIP_CAP_DAILY",
    "DECISION_SKIP_CAP_MONTHLY",
    "DECISION_SKIP_CAP_CATEGORY",
    "DECISION_SKIP_DISABLED",
    "DECISION_SKIP_DISTRESS",
    "DECISION_SKIP_INPUT_TOO_LARGE",
    "DECISION_SKIP_CIRCUIT_OPEN",
    "DECISION_ERROR",
]
