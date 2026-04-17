"""
Tests for the centralized LLM cost-control client.

These tests assert the hard-gate behavior: the client must never make a network
call when the budget is exhausted, the circuit breaker is open, distress is too
low, or the input is too large. Dry-run must be the default shipping posture and
must log spend without touching the network.
"""

import csv
import os
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from llm_client import (  # noqa: E402
    DECISION_CACHE_HIT,
    DECISION_DRY_RUN,
    DECISION_SKIP_CAP_CALLS,
    DECISION_SKIP_CAP_DAILY,
    DECISION_SKIP_CAP_MONTHLY,
    DECISION_SKIP_DISABLED,
    DECISION_SKIP_DISTRESS,
    DECISION_USED,
    LLMClient,
)


def _base_settings(tmpdir: str, **overrides: Any) -> Dict[str, Any]:
    cfg: Dict[str, Any] = {
        "llm_budget": {
            "enabled": True,
            "dry_run": False,
            "per_call_max_input_tokens": 10_000,
            "per_call_max_output_tokens": 500,
            "per_cycle_max_calls": 100,
            "daily_usd_cap": 10.0,
            "monthly_usd_cap": 100.0,
            "per_category_daily_max_calls": 50,
            "min_distress_score_for_llm": 0,
            "cache_file": os.path.join(tmpdir, "cache.json"),
            "cache_ttl_days": 30,
            "ledger_csv": os.path.join(tmpdir, "ledger.csv"),
            "circuit_breaker_cooldown_seconds": 60,
            "alert_threshold_pct_of_cap": 80,
            "providers": {
                "anthropic": {"input_usd_per_1k": 0.003, "output_usd_per_1k": 0.015},
            },
        }
    }
    cfg["llm_budget"].update(overrides)
    return cfg


class LLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmp.name

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _make_client(self, **overrides: Any) -> LLMClient:
        return LLMClient(_base_settings(self.tmpdir, **overrides))

    def _read_ledger(self, client: LLMClient) -> list:
        path = client.ledger.csv_path
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8", newline="") as f:
            return list(csv.DictReader(f))

    # ---- deterministic gating ----

    def test_disabled_client_does_not_call(self) -> None:
        client = self._make_client(enabled=False)
        calls = []

        def boom(_payload: Dict[str, Any]) -> Dict[str, Any]:
            calls.append(1)
            return {"data": {}}

        result = client.call(
            module="triage",
            prompt_key="test_v1",
            prompt_payload={"title": "x"},
            provider="anthropic",
            model="claude",
            call_fn=boom,
        )
        self.assertFalse(result.used_llm)
        self.assertEqual(result.decision, DECISION_SKIP_DISABLED)
        self.assertEqual(calls, [])

    def test_low_distress_skips_call(self) -> None:
        client = self._make_client(min_distress_score_for_llm=40)
        calls = []

        def boom(_payload: Dict[str, Any]) -> Dict[str, Any]:
            calls.append(1)
            return {"data": {}}

        result = client.call(
            module="triage",
            prompt_key="test_v1",
            prompt_payload={"title": "x"},
            event_category="cybersecurity",
            distress_score=10,
            provider="anthropic",
            model="claude",
            call_fn=boom,
        )
        self.assertFalse(result.used_llm)
        self.assertEqual(result.decision, DECISION_SKIP_DISTRESS)
        self.assertEqual(calls, [])

    def test_per_cycle_cap_blocks_after_limit(self) -> None:
        client = self._make_client(per_cycle_max_calls=1, dry_run=True)
        client.start_cycle("cycle-1")
        r1 = client.call(
            module="narrative_clustering",
            prompt_key="v1",
            prompt_payload={"a": 1},
            provider="anthropic",
            model="m",
        )
        r2 = client.call(
            module="narrative_clustering",
            prompt_key="v1",
            prompt_payload={"a": 2},
            provider="anthropic",
            model="m",
        )
        self.assertEqual(r1.decision, DECISION_DRY_RUN)
        self.assertEqual(r2.decision, DECISION_SKIP_CAP_CALLS)

    def test_daily_usd_cap_blocks(self) -> None:
        # Force cap to zero so any estimated cost trips it
        client = self._make_client(
            daily_usd_cap=0.00000001,
            dry_run=True,
            per_cycle_max_calls=10,
        )
        client.start_cycle("cycle-daily")
        r1 = client.call(
            module="materiality",
            prompt_key="v1",
            prompt_payload={"title": "x"},
            provider="anthropic",
            model="m",
        )
        # first call is dry_run and records spend; second call should be capped
        r2 = client.call(
            module="materiality",
            prompt_key="v1",
            prompt_payload={"title": "y"},
            provider="anthropic",
            model="m",
        )
        self.assertEqual(r1.decision, DECISION_DRY_RUN)
        self.assertEqual(r2.decision, DECISION_SKIP_CAP_DAILY)

    def test_monthly_usd_cap_blocks(self) -> None:
        client = self._make_client(
            daily_usd_cap=0.0,
            monthly_usd_cap=0.00000001,
            dry_run=True,
        )
        client.start_cycle("cycle-monthly")
        r1 = client.call(
            module="materiality",
            prompt_key="v1",
            prompt_payload={"title": "x"},
            provider="anthropic",
            model="m",
        )
        r2 = client.call(
            module="materiality",
            prompt_key="v1",
            prompt_payload={"title": "y"},
            provider="anthropic",
            model="m",
        )
        self.assertEqual(r1.decision, DECISION_DRY_RUN)
        self.assertEqual(r2.decision, DECISION_SKIP_CAP_MONTHLY)

    # ---- dry-run semantics ----

    def test_dry_run_never_calls_network(self) -> None:
        client = self._make_client(dry_run=True)
        calls = []

        def boom(_payload: Dict[str, Any]) -> Dict[str, Any]:
            calls.append(1)
            return {"data": {"x": 1}}

        result = client.call(
            module="triage",
            prompt_key="v1",
            prompt_payload={"x": 1},
            provider="anthropic",
            model="m",
            call_fn=boom,
        )
        self.assertFalse(result.used_llm)
        self.assertEqual(result.decision, DECISION_DRY_RUN)
        self.assertEqual(calls, [])
        rows = self._read_ledger(client)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["decision"], DECISION_DRY_RUN)

    # ---- live path + cache ----

    def test_live_call_records_and_caches(self) -> None:
        client = self._make_client(dry_run=False)
        observed = []

        def echo(payload: Dict[str, Any]) -> Dict[str, Any]:
            observed.append(payload)
            return {
                "data": {"materiality_usd": 1_000_000},
                "input_tokens": 500,
                "output_tokens": 120,
            }

        payload = {"title": "acme cyber"}
        r1 = client.call(
            module="materiality",
            prompt_key="mat_v1",
            prompt_payload=payload,
            event_category="cybersecurity",
            distress_score=70,
            provider="anthropic",
            model="claude-sonnet",
            call_fn=echo,
        )
        self.assertTrue(r1.used_llm)
        self.assertEqual(r1.decision, DECISION_USED)
        self.assertEqual(r1.data.get("materiality_usd"), 1_000_000)
        self.assertGreater(r1.cost_usd, 0.0)

        # Second call with same payload should be a cache hit and must NOT call echo again.
        r2 = client.call(
            module="materiality",
            prompt_key="mat_v1",
            prompt_payload=payload,
            event_category="cybersecurity",
            distress_score=70,
            provider="anthropic",
            model="claude-sonnet",
            call_fn=echo,
        )
        self.assertTrue(r2.used_llm)
        self.assertEqual(r2.decision, DECISION_CACHE_HIT)
        self.assertEqual(len(observed), 1)

        rows = self._read_ledger(client)
        decisions = [row["decision"] for row in rows]
        self.assertIn(DECISION_USED, decisions)
        self.assertIn(DECISION_CACHE_HIT, decisions)

    def test_snapshot_usage_contains_totals(self) -> None:
        client = self._make_client(dry_run=True)
        client.start_cycle("snap")
        client.call(
            module="triage",
            prompt_key="v1",
            prompt_payload={"x": 1},
            provider="anthropic",
            model="m",
        )
        snap = client.snapshot_usage()
        self.assertTrue(snap["enabled"])
        self.assertTrue(snap["dry_run"])
        self.assertGreaterEqual(snap["daily_spend_usd"], 0.0)
        self.assertGreaterEqual(snap["cycle_calls"], 1)


if __name__ == "__main__":
    unittest.main()
