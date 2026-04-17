"""
Tests for the signal freshness guardrail.
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from freshness_guardrail import FreshnessVerdict, evaluate  # noqa: E402


class _FakeLLMResult:
    def __init__(self, allow: bool, reason: str = "", evidence: list = None) -> None:
        self.used_llm = True
        self.data = {
            "allow_alert": allow,
            "reason": reason,
            "evidence": evidence or [],
        }
        self.decision = "used"


class _FakeLLMClient:
    def __init__(self, allow: bool) -> None:
        self.calls = []
        self._allow = allow

    def call(self, **kwargs: Any) -> _FakeLLMResult:
        self.calls.append(kwargs)
        return _FakeLLMResult(self._allow, reason="llm_override")


class FreshnessGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 4, 16, 12, 0, tzinfo=timezone.utc)

    def test_stale_article_blocks_alert(self) -> None:
        event = {
            "event_category": "cybersecurity",
            "published": (self.now - timedelta(hours=100)).isoformat(),
            "title": "Acme material cybersecurity incident",
        }
        verdict = evaluate(
            event=event,
            recent_headlines=[],
            now=self.now,
            max_article_age_hours=72,
        )
        self.assertFalse(verdict.allow_alert)
        self.assertTrue(verdict.stale)

    def test_clinical_reversal_blocks_alert(self) -> None:
        event = {
            "event_category": "clinical_regulatory_binary",
            "published": self.now.isoformat(),
            "title": "FDA issues complete response letter",
        }
        later_headline = {
            "title": "FDA rescinds CRL and approves drug",
            "summary": "Regulator approves the therapy after further review.",
            "published": (self.now - timedelta(hours=2)).isoformat(),
        }
        verdict = evaluate(
            event=event,
            recent_headlines=[later_headline],
            now=self.now,
            max_article_age_hours=72,
            freshness_window_hours=24,
        )
        self.assertFalse(verdict.allow_alert)
        self.assertEqual(verdict.reason, "reversal_detected")
        self.assertTrue(verdict.evidence)

    def test_no_reversal_allows_alert(self) -> None:
        event = {
            "event_category": "cybersecurity",
            "published": self.now.isoformat(),
            "title": "Acme material cybersecurity incident",
        }
        headlines = [
            {
                "title": "Acme investigating cyber incident",
                "summary": "Company says investigation is ongoing.",
                "published": (self.now - timedelta(hours=2)).isoformat(),
            }
        ]
        verdict = evaluate(
            event=event,
            recent_headlines=headlines,
            now=self.now,
            max_article_age_hours=72,
        )
        self.assertTrue(verdict.allow_alert)

    def test_reversal_outside_window_is_ignored(self) -> None:
        event = {
            "event_category": "cybersecurity",
            "published": self.now.isoformat(),
        }
        old_reversal = {
            "title": "Acme services restored weeks ago",
            "summary": "Historical article should not affect freshness.",
            "published": (self.now - timedelta(hours=200)).isoformat(),
        }
        verdict = evaluate(
            event=event,
            recent_headlines=[old_reversal],
            now=self.now,
            max_article_age_hours=72,
            freshness_window_hours=24,
        )
        self.assertTrue(verdict.allow_alert)

    def test_llm_override_blocks(self) -> None:
        event = {
            "event_category": "cybersecurity",
            "published": self.now.isoformat(),
            "distress_score": 80,
        }
        headlines = [
            {
                "title": "Acme investigating cyber incident",
                "summary": "Company says situation is contained but not resolved.",
                "published": (self.now - timedelta(hours=1)).isoformat(),
            }
        ]
        fake = _FakeLLMClient(allow=False)
        verdict = evaluate(
            event=event,
            recent_headlines=headlines,
            now=self.now,
            llm_client=fake,
        )
        self.assertFalse(verdict.allow_alert)
        self.assertEqual(verdict.engine, "agent")
        self.assertTrue(fake.calls)


if __name__ == "__main__":
    unittest.main()
