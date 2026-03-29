"""
Container health check utility.

Reads data/runtime_heartbeat.json and exits non-zero when:
- no heartbeat exists
- heartbeat is stale
- last cycle status is error
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--max-age-seconds",
        type=int,
        default=int(os.environ.get("CATASTROPHE_HEALTH_MAX_AGE_SECONDS", "2400")),
        help="Max allowed heartbeat age in seconds",
    )
    parser.add_argument(
        "--heartbeat-path",
        default="../data/runtime_heartbeat.json",
        help="Path to runtime heartbeat json",
    )
    args = parser.parse_args()

    path = args.heartbeat_path
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join(os.path.dirname(__file__), path))

    if not os.path.exists(path):
        print(f"HEALTHCHECK FAIL: heartbeat file missing: {path}")
        return 1

    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"HEALTHCHECK FAIL: cannot read heartbeat: {exc}")
        return 1

    ts_raw = str(payload.get("timestamp", "")).strip()
    status = str(payload.get("status", "")).strip().lower()
    if not ts_raw:
        print("HEALTHCHECK FAIL: heartbeat timestamp missing")
        return 1

    try:
        ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
    except ValueError:
        print(f"HEALTHCHECK FAIL: invalid timestamp format: {ts_raw}")
        return 1

    age_seconds = (datetime.now(timezone.utc) - ts).total_seconds()
    if age_seconds > max(60, int(args.max_age_seconds)):
        print(f"HEALTHCHECK FAIL: heartbeat stale age={age_seconds:.0f}s")
        return 1

    if status == "error":
        err = str(payload.get("error", "")).strip()
        print(f"HEALTHCHECK FAIL: last cycle error: {err or '(unknown)'}")
        return 1

    print(f"HEALTHCHECK OK: status={status or 'ok'} age={age_seconds:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
