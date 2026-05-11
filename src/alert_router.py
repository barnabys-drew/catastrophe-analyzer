"""Horizon-based Discord alert router (Task #49 sub-piece 1).

Stdlib-only. Vendor this file into any service that posts to Discord:
    cp ~/code/argus-directive/lib/alert_router.py <service>/src/

Public API:
    route(webhook_url, payload, *, horizon, dead_letter_path=None,
          source="unknown", spool_path=None) -> bool
        Route a Discord-bound payload based on its trade horizon.
        - horizon='urgent' → immediate post via discord_safe.safe_post
        - horizon='swing'  → append to spool for 5-min clustering (daemon ships in sub-piece 2)
        - horizon='long'   → append to spool for daily-digest clustering (sub-piece 2)

        On spool path failure or unknown horizon, the alert is treated as
        urgent and posted immediately — never lose an alert because of a
        clustering failure (spec line 491).

Why JSONL spool:
- Append-only; one record per alert.
- Atomic writes via O_APPEND + fsync (same pattern as discord_safe DL).
- Daemon (sub-piece 2) reads, batches by ticker+horizon, flushes on timer.
- A crashed daemon doesn't lose alerts — the next start drains the spool.

Spool record schema:
    {
        "ts": "2026-05-10T05:42:00Z",       # when routed
        "source": "uam",                     # routing service
        "horizon": "swing",                  # routing tier
        "ticker": "NVDA",                    # extracted for per-ticker grouping; "" if absent
        "webhook_url": "https://...",        # daemon reads this to know where to flush
        "payload": { ... },                  # the original Discord body
    }

Horizon tier definitions (from Task #49 spec, Drew's 2026-05-10 verbatim):
- urgent — research-analyst recommendations, same-day-action signals,
           breaking-news catastrophe events. Bypass clustering, post now.
- swing  — UAM unusual-activity, argus trade posts, macro signals targeting
           1-5 day holds. 5-minute window for clustering.
- long   — portfolio-analyzer rebalance, gold-monitor BUY verdicts,
           concentration alerts. Daily digest (4pm ET flush).
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger("alert_router")

# Canonical horizon set. Anything else falls back to urgent (= direct post).
HORIZONS = ("urgent", "swing", "long")


def _clustering_enabled() -> bool:
    """Is the aggregator daemon expected to be reading the spool?

    Operators flip this on (`ALERT_ROUTER_CLUSTERING_ENABLED=1`) once the
    `alert_aggregator.py` daemon is running. Until then, treating swing/long
    as 'spool and forget' would silently lose every clustered alert because
    nothing drains the queue. Defaulting OFF means migrating a service to
    `alert_router.route(...)` is safe even if the daemon hasn't been wired
    yet — every horizon falls through to immediate Discord post.

    Spec contract (line 491): "Falls back to direct post if the aggregator
    is down — never lose an alert because of a clustering failure."
    """
    val = os.environ.get("ALERT_ROUTER_CLUSTERING_ENABLED", "").strip().lower()
    return val in ("1", "true", "yes", "on")

# Default spool location. Overridable via ALERT_ROUTER_SPOOL env var or
# explicit `spool_path=` kwarg. Living in ~/code/.claude/ aligns with
# missed_alerts.jsonl + cycle_count.txt so all loop state is co-located.
DEFAULT_SPOOL = Path(os.environ.get(
    "ALERT_ROUTER_SPOOL",
    "/home/drewt_p_weiner/code/.claude/pending_alerts.jsonl",
))


def _extract_ticker(payload: dict) -> str:
    """Best-effort ticker extraction from a Discord payload.

    The aggregator daemon (sub-piece 2) groups by ticker so multi-source
    signals on the same name collapse into one rich embed. We check the
    top-level payload first, then embed fields/title, then return "" if
    nothing looks like a ticker. False positives are OK — the daemon
    treats "" as "ungrouped" so they just don't collapse with anything.
    """
    if not isinstance(payload, dict):
        return ""
    direct = payload.get("ticker")
    if isinstance(direct, str) and direct.strip():
        return direct.strip().upper()
    # Look in embeds for a "ticker" field
    embeds = payload.get("embeds")
    if isinstance(embeds, list):
        for e in embeds:
            if not isinstance(e, dict):
                continue
            t = e.get("ticker")
            if isinstance(t, str) and t.strip():
                return t.strip().upper()
            for fld in e.get("fields", []) or []:
                if not isinstance(fld, dict):
                    continue
                if str(fld.get("name", "")).strip().lower() == "ticker":
                    val = str(fld.get("value", "")).strip().upper()
                    if val:
                        return val
    return ""


def _append_spool(spool_path: Path, record: dict) -> bool:
    """Append-only write to the spool JSONL with fsync. Returns True on success.

    Uses os.write/os.fsync rather than `open(...).write(...)` to ensure the
    record hits disk before the function returns. The daemon may be reading
    the file concurrently and we want consistent end-of-file state.
    """
    try:
        spool_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(spool_path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(record) + "\n").encode("utf-8"))
            os.fsync(fd)
        finally:
            os.close(fd)
        return True
    except OSError as e:
        log.warning("alert_router: spool write failed %s — %s", spool_path, e)
        return False


def route(
    webhook_url: str,
    payload: dict,
    *,
    horizon: str,
    dead_letter_path: Optional[str] = None,
    source: str = "unknown",
    spool_path: Optional[Path] = None,
) -> bool:
    """Route an alert based on its horizon.

    Returns True if the alert was either posted (urgent) or successfully
    spooled (swing/long). Returns False only on hard delivery failure for
    urgent alerts, matching discord_safe.safe_post semantics.

    Fallback policy: an unknown horizon, a spool-write failure, or a missing
    spool_path all fall through to immediate posting. Never silently drop.
    """
    horizon_norm = (horizon or "").strip().lower()
    spool = Path(spool_path) if spool_path else DEFAULT_SPOOL

    if horizon_norm not in HORIZONS:
        log.warning(
            "alert_router: unknown horizon %r from source=%s — posting immediately",
            horizon, source,
        )
        horizon_norm = "urgent"

    # Clustering kill-switch: if the aggregator daemon isn't running, every
    # horizon falls through to direct post. Lets services migrate to
    # alert_router calls safely BEFORE the daemon is deployed.
    if not _clustering_enabled() and horizon_norm != "urgent":
        log.debug(
            "alert_router: clustering disabled — posting %s alert from %s immediately",
            horizon_norm, source,
        )
        return _post_now(webhook_url, payload, dead_letter_path=dead_letter_path, source=source)

    if horizon_norm == "urgent":
        return _post_now(webhook_url, payload, dead_letter_path=dead_letter_path, source=source)

    # swing / long → spool for the aggregator daemon
    record = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "source": source,
        "horizon": horizon_norm,
        "ticker": _extract_ticker(payload),
        "webhook_url": webhook_url,
        "payload": payload,
    }
    if _append_spool(spool, record):
        return True

    # Spool failed (disk full? permissions?) — fall through to direct post.
    log.warning(
        "alert_router: spool failed for horizon=%s source=%s — fallback to direct post",
        horizon_norm, source,
    )
    return _post_now(webhook_url, payload, dead_letter_path=dead_letter_path, source=source)


def _post_now(
    webhook_url: str,
    payload: dict,
    *,
    dead_letter_path: Optional[str],
    source: str,
) -> bool:
    """Thin wrapper around discord_safe.safe_post that does the import lazily.

    Lazy import keeps alert_router importable in environments where
    discord_safe hasn't been vendored yet (unit tests, dry-run callers).
    """
    try:
        import discord_safe  # type: ignore
    except ImportError:
        log.error(
            "alert_router: discord_safe not importable; cannot deliver urgent alert "
            "from source=%s", source,
        )
        return False
    return discord_safe.safe_post(
        webhook_url,
        payload,
        dead_letter_path=dead_letter_path,
        source=source,
    )
