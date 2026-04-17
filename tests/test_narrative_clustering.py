"""
Tests for the narrative clustering enricher.

Goals:
- Deterministic pass must dedupe near-identical cross-source headlines.
- Distinct stories must not merge.
- Time window and category guardrails hold.
- LLM refinement is only consulted inside the configured similarity band and
  always falls back to the deterministic decision when the client abstains.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from narrative_clustering import (  # noqa: E402
    canonical_articles,
    cluster_articles,
)


class _FakeLLMResult:
    def __init__(self, same_event: bool) -> None:
        self.used_llm = True
        self.data = {"same_event": same_event}
        self.decision = "used"


class _FakeLLMClient:
    def __init__(self, same_event: bool = True) -> None:
        self.calls: List[Dict[str, Any]] = []
        self._same_event = same_event

    def call(self, **kwargs: Any) -> _FakeLLMResult:
        self.calls.append(kwargs)
        return _FakeLLMResult(self._same_event)


class _AbstainingLLMClient:
    def __init__(self) -> None:
        self.calls: List[Dict[str, Any]] = []

    def call(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        # LLMClient returns used_llm=False on cap/dry-run; simulate that here.
        class _Abstain:
            used_llm = False
            data = {}
            decision = "skipped_daily_cap"

        return _Abstain()


class NarrativeClusteringTests(unittest.TestCase):
    def test_duplicate_headlines_merge(self) -> None:
        articles = [
            {
                "title": "Acme discloses material cybersecurity incident",
                "summary": "Ransomware attack reported in SEC filing.",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "https://feed-a.example/1",
                "published": "2026-04-16T12:00:00Z",
            },
            {
                "title": "Acme Inc. discloses material cybersecurity incident",
                "summary": "Ransomware attack confirmed.",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "https://feed-b.example/2",
                "published": "2026-04-16T13:00:00Z",
            },
            {
                "title": "Acme - material cybersecurity incident after ransomware",
                "summary": "Company filed 8-K disclosure.",
                "event_category": "cybersecurity",
                "tickers": ["ACME"],
                "link": "https://feed-c.example/3",
                "published": "2026-04-16T14:00:00Z",
            },
        ]
        clusters = cluster_articles(articles)
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.size(), 3)
        self.assertEqual(
            sorted(cluster.source_urls),
            sorted([a["link"] for a in articles]),
        )
        self.assertIn("ACME", cluster.tickers)

    def test_different_stories_do_not_merge(self) -> None:
        articles = [
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "a",
                "published": "2026-04-16T12:00:00Z",
            },
            {
                "title": "BetaCo announces guidance raise after record revenue",
                "event_category": "positive_earnings_catalyst",
                "ticker": "BETA",
                "link": "b",
                "published": "2026-04-16T12:30:00Z",
            },
            {
                "title": "Gamma files Chapter 11 after covenant default",
                "event_category": "financial_distress",
                "ticker": "GAM",
                "link": "c",
                "published": "2026-04-16T13:00:00Z",
            },
        ]
        clusters = cluster_articles(articles)
        self.assertEqual(len(clusters), 3)
        sizes = sorted(c.size() for c in clusters)
        self.assertEqual(sizes, [1, 1, 1])

    def test_time_window_prevents_merge(self) -> None:
        articles = [
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "a",
                "published": "2026-04-10T12:00:00Z",
            },
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "b",
                "published": "2026-04-16T12:00:00Z",
            },
        ]
        clusters = cluster_articles(articles, time_window_hours=24)
        self.assertEqual(len(clusters), 2)

    def test_different_categories_stay_separate(self) -> None:
        articles = [
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "a",
                "published": "2026-04-16T12:00:00Z",
            },
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "fraud_accounting_enforcement",
                "ticker": "ACME",
                "link": "b",
                "published": "2026-04-16T12:15:00Z",
            },
        ]
        clusters = cluster_articles(articles)
        self.assertEqual(len(clusters), 2)

    def test_llm_refinement_band_merges_on_same_event(self) -> None:
        articles = [
            {
                "title": "BetaCo profit warning rattles sector",
                "event_category": "negative_earnings_catalyst",
                "ticker": "BETA",
                "link": "a",
                "published": "2026-04-16T12:00:00Z",
            },
            # Lower token overlap than threshold but clearly about the same event.
            {
                "title": "BetaCo shares tumble after guidance cut",
                "event_category": "negative_earnings_catalyst",
                "ticker": "BETA",
                "link": "b",
                "published": "2026-04-16T12:30:00Z",
            },
        ]
        fake = _FakeLLMClient(same_event=True)
        clusters = cluster_articles(
            articles,
            similarity_threshold=0.80,
            llm_refine_band=(0.10, 0.80),
            llm_client=fake,
        )
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].decision, "llm_refined")
        self.assertTrue(fake.calls)

    def test_llm_refinement_abstain_falls_back_to_deterministic(self) -> None:
        articles = [
            {
                "title": "BetaCo profit warning rattles sector",
                "event_category": "negative_earnings_catalyst",
                "ticker": "BETA",
                "link": "a",
                "published": "2026-04-16T12:00:00Z",
            },
            {
                "title": "BetaCo shares tumble after guidance cut",
                "event_category": "negative_earnings_catalyst",
                "ticker": "BETA",
                "link": "b",
                "published": "2026-04-16T12:30:00Z",
            },
        ]
        abstain = _AbstainingLLMClient()
        clusters = cluster_articles(
            articles,
            similarity_threshold=0.80,
            llm_refine_band=(0.10, 0.80),
            llm_client=abstain,
        )
        # Deterministic similarity is below threshold; with LLM abstaining, the
        # two articles must remain in separate clusters.
        self.assertEqual(len(clusters), 2)
        self.assertTrue(abstain.calls)

    def test_canonical_articles_carry_metadata(self) -> None:
        articles = [
            {
                "title": "Acme discloses material cybersecurity incident",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "a",
                "published": "2026-04-16T12:00:00Z",
            },
            {
                "title": "Acme Inc. material cybersecurity incident confirmed",
                "event_category": "cybersecurity",
                "ticker": "ACME",
                "link": "b",
                "published": "2026-04-16T12:30:00Z",
            },
        ]
        clusters = cluster_articles(articles)
        canon = canonical_articles(articles, clusters)
        self.assertEqual(len(canon), 1)
        art = canon[0]
        self.assertIn("narrative_cluster_id", art)
        self.assertEqual(art["narrative_cluster_size"], 2)
        self.assertEqual(sorted(art["narrative_source_urls"]), ["a", "b"])


if __name__ == "__main__":
    unittest.main()
