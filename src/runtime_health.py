"""
Runtime heartbeat helpers for Docker health checks.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from typing import Dict, Optional


def _heartbeat_path(repo_root: str) -> str:
    return os.path.join(repo_root, "data", "runtime_heartbeat.json")


def write_runtime_heartbeat(
    *,
    repo_root: str,
    status: str,
    summary: Optional[Dict] = None,
    error: str = "",
) -> None:
    """
    Persist the most recent cycle state for health monitoring.
    """
    path = _heartbeat_path(repo_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "error": error,
        "summary": summary or {},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
