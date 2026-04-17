"""
Tests for materiality extraction + triage integration.
"""

import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


from impact_triage import ImpactTriage  # noqa: E402
from materiality_extraction import (  # noqa: E402
    extract,
    materiality_impact_bonus,
)


class MaterialityExtractionTests(unittest.TestCase):
    def test_extracts_usd_million(self) -> None:
        result = extract(
            {
                "title": "Acme expects $250 million loss from cyber incident",
                "summary": "Company estimates remediation costs of $250 million.",
                "event_category": "cybersecurity",
            }
        )
        self.assertIsNotNone(result.materiality_usd)
        self.assertGreaterEqual(result.materiality_usd, 250_000_000.0)
        self.assertGreaterEqual(materiality_impact_bonus(result), 5)

    def test_extracts_usd_billion(self) -> None:
        result = extract(
            {
                "title": "Fine issued: $1.5B penalty for accounting violations",
                "summary": "SEC announces $1.5 billion settlement.",
                "event_category": "fraud_accounting_enforcement",
            }
        )
        self.assertIsNotNone(result.materiality_usd)
        self.assertGreaterEqual(result.materiality_usd, 1_500_000_000.0)

    def test_extracts_pct_revenue(self) -> None:
        result = extract(
            {
                "title": "Recall affects products representing 12% of revenue",
                "summary": "Company says product line is 12% of annual revenue.",
                "event_category": "product_safety_recall",
            }
        )
        self.assertIsNotNone(result.materiality_pct_revenue)
        self.assertGreaterEqual(result.materiality_pct_revenue, 12.0)

    def test_extracts_unit_count(self) -> None:
        result = extract(
            {
                "title": "Breach exposed 5 million customer records",
                "summary": "Hacker accessed 5 million records from the company's systems.",
                "event_category": "cybersecurity",
            }
        )
        self.assertIsNotNone(result.materiality_unit_count)
        self.assertGreaterEqual(result.materiality_unit_count, 5_000_000)

    def test_no_materiality_returns_none(self) -> None:
        result = extract(
            {
                "title": "Company announces leadership transition",
                "summary": "CEO to step down in coming months.",
                "event_category": "leadership_scandal",
            }
        )
        self.assertIsNone(result.materiality_usd)
        self.assertIsNone(result.materiality_pct_revenue)
        self.assertIsNone(result.materiality_unit_count)
        self.assertEqual(materiality_impact_bonus(result), 0)

    def test_triage_applies_materiality_bonus(self) -> None:
        triage = ImpactTriage({"triage": {"enabled": True, "agent_enabled": False}})

        low_materiality = triage.evaluate(
            {
                "title": "Company files 8-K on material cybersecurity incident",
                "summary": "Ransomware attack disrupted operations.",
                "event_category": "cybersecurity",
                "distress_score": 55,
            }
        )
        high_materiality = triage.evaluate(
            {
                "title": "Company files 8-K on material cybersecurity incident; 12 million records exposed",
                "summary": "Ransomware attack disrupted operations; $500 million remediation estimate.",
                "event_category": "cybersecurity",
                "distress_score": 55,
            }
        )
        self.assertGreater(
            high_materiality["impact_score"], low_materiality["impact_score"]
        )


if __name__ == "__main__":
    unittest.main()
