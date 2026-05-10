"""Discord webhook posting with retry + dead-letter (Task #35).

Stdlib-only. Vendor this file into any service that posts to Discord:
    cp ~/code/argus-directive/lib/discord_safe.py <service>/src/

Public API:
    safe_post(webhook_url, payload, *, dead_letter_path=None,
              max_attempts=3, source="unknown") -> bool
        Post a JSON payload to Discord with up to max_attempts retries on
        transient errors (429/5xx/connection). On terminal failure, append
        the payload (with metadata) to dead_letter_path for later replay.
        Returns True on success, False on terminal failure.

    replay(webhook_url, dead_letter_path, *, max_replays=50) -> tuple[int, int]
        Read pending dead-letter entries, retry each. Successful retries are
        removed; failures stay queued. Returns (replayed_count, still_failed).

Why dead-letter format is JSONL:
- Append-only: corrupting one line doesn't kill the queue.
- Easy to truncate or rewrite atomically.
- One record = one failed alert; metadata travels with it.

Dead-letter record schema:
    {
        "ts": "2026-05-10T05:42:00Z",       # when added to DL
        "source": "lego-monitor",            # vendoring service
        "payload": { ... },                  # the original JSON body
        "reason": "HTTP 503: ...",           # last failure reason
        "attempts": 3                        # how many tries already
    }
"""

from __future__ import annotations

import contextlib
import json
import os
import tempfile
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

USER_AGENT = "argus-discord-safe/1.0"
TRANSIENT_HTTP = {408, 429, 500, 502, 503, 504}


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _post_once(webhook_url: str, payload: dict[str, Any], timeout: int = 10) -> tuple[bool, str]:
    """Single POST attempt. Returns (ok, reason)."""
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            code = resp.getcode()
            if 200 <= code < 300:
                return True, f"HTTP {code}"
            return False, f"HTTP {code} (transient={code in TRANSIENT_HTTP})"
    except urllib.error.HTTPError as e:
        transient = e.code in TRANSIENT_HTTP
        return False, f"HTTPError {e.code} (transient={transient})"
    except urllib.error.URLError as e:
        return False, f"URLError: {e.reason}"
    except Exception as e:
        return False, f"Exception: {type(e).__name__}: {e}"


def _is_transient_reason(reason: str) -> bool:
    """Should this failure be retried?"""
    # Network blips (URLError/Exception) plus our own "transient=True" tag.
    return "URLError" in reason or "Exception" in reason or "transient=True" in reason


def _append_dead_letter(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
        f.flush()
        os.fsync(f.fileno())


def safe_post(
    webhook_url: str,
    payload: dict[str, Any],
    *,
    dead_letter_path: str | os.PathLike | None = None,
    max_attempts: int = 3,
    source: str = "unknown",
) -> bool:
    """Post a JSON payload to Discord with retry + dead-letter on terminal failure."""
    if not webhook_url:
        return False
    last_reason = ""
    for attempt in range(1, max_attempts + 1):
        ok, reason = _post_once(webhook_url, payload)
        if ok:
            return True
        last_reason = reason
        if not _is_transient_reason(reason):
            break  # 4xx (except 408/429) is a content error; retrying won't help
        if attempt < max_attempts:
            time.sleep(min(2 ** (attempt - 1), 4))  # 1s, 2s, 4s cap

    if dead_letter_path:
        _append_dead_letter(
            Path(dead_letter_path),
            {
                "ts": _now_iso(),
                "source": source,
                "payload": payload,
                "reason": last_reason,
                "attempts": max_attempts,
            },
        )
    return False


def _atomic_write_jsonl(path: Path, records: list[dict]) -> None:
    """Rewrite the dead-letter file atomically with the surviving records."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=path.name + ".", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def replay(
    webhook_url: str,
    dead_letter_path: str | os.PathLike,
    *,
    max_replays: int = 50,
) -> tuple[int, int]:
    """Replay queued failed posts. Returns (replayed_ok, still_failed)."""
    path = Path(dead_letter_path)
    if not path.exists():
        return 0, 0
    try:
        with open(path, encoding="utf-8") as f:
            records = [json.loads(line) for line in f if line.strip()]
    except (OSError, json.JSONDecodeError):
        return 0, 0
    if not records:
        return 0, 0

    replayed = 0
    survivors: list[dict] = []
    for rec in records:
        if replayed >= max_replays:
            survivors.append(rec)
            continue
        payload = rec.get("payload") or {}
        ok, reason = _post_once(webhook_url, payload)
        if ok:
            replayed += 1
        else:
            rec["reason"] = reason
            rec["attempts"] = int(rec.get("attempts", 0)) + 1
            survivors.append(rec)

    _atomic_write_jsonl(path, survivors)
    return replayed, len(survivors)


__all__ = ["replay", "safe_post"]
