"""
Category / triage regression tests.

Module name uses `test_z_` so unittest discover imports this file *after*
`test_entity_extractor_precision.py`. Otherwise `_install_main_import_stubs()` below
would replace `entity_extractor` in sys.modules before precision tests load.
"""
import json
import sys
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def _install_main_import_stubs() -> None:
    """Stub heavy runtime modules so `main` can be imported in isolation."""
    module_to_class = {
        "news_scraper": "NewsScraper",
        "entity_extractor": "EntityExtractor",
        "stock_analyzer": "StockAnalyzer",
        "signal_generator": "SignalGenerator",
    }

    for module_name, class_name in module_to_class.items():
        mod = types.ModuleType(module_name)

        class _Stub:
            def __init__(self, *args, **kwargs):
                pass

        setattr(mod, class_name, _Stub)
        sys.modules[module_name] = mod


_install_main_import_stubs()

from impact_triage import ImpactTriage  # noqa: E402
from main import CatastropheAnalyzerApp  # noqa: E402


class ClassificationRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Avoid full runtime initialization; these helpers are pure string heuristics.
        cls.app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)

    def test_cybersecurity_subtype_material_disclosure(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Acme files 8-K on material cybersecurity incident after unauthorized access",
            summary="Company disclosed service outage and SEC filing details.",
            event_category="cybersecurity",
        )
        self.assertEqual(subtype, "Material Cyber Disclosure")
        self.assertEqual(severity, "High")

    def test_clinical_subtype_partial_hold(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="BiotechCo receives partial clinical hold from FDA",
            summary="Regulator cited safety signal and trial protocol concerns.",
            event_category="clinical_regulatory_binary",
        )
        self.assertEqual(subtype, "Partial Clinical Hold")
        self.assertEqual(severity, "High")

    def test_product_safety_subtype_class_i_recall(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="DeviceCo announces Class I recall after serious injury reports",
            summary="Regulator issued do-not-use communication.",
            event_category="product_safety_recall",
        )
        self.assertEqual(subtype, "Class I Recall")
        self.assertEqual(severity, "High")

    def test_fraud_subtype_sec_enforcement(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="SEC charges WidgetCo and two executives with securities fraud",
            summary="Civil complaint alleges misstated revenue and internal control failures.",
            event_category="fraud_accounting_enforcement",
        )
        self.assertEqual(subtype, "SEC Enforcement Action")
        self.assertEqual(severity, "High")

    def test_supply_chain_subtype_factory_disruption(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="PartsCo halts production after factory fire at key plant",
            summary="Company cites damage assessment and supply chain disruption.",
            event_category="supply_chain_disruption",
        )
        self.assertEqual(subtype, "Factory/Plant Disruption")
        self.assertEqual(severity, "High")

    def test_financial_distress_subtype_chapter_11(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="RetailCo files Chapter 11 after liquidity crunch",
            summary="Company seeks debtor-in-possession financing.",
            event_category="financial_distress",
        )
        self.assertEqual(subtype, "Chapter 11 Restructuring")
        self.assertEqual(severity, "High")

    def test_dilutive_financing_subtype_registered_direct(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="BioCo prices registered direct offering with warrants",
            summary="Capital raise priced at discount to market.",
            event_category="dilutive_financing",
        )
        self.assertEqual(subtype, "Registered Direct Offering")
        self.assertEqual(severity, "High")

    def test_ma_subtype_hostile_bid(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Bidder launches hostile bid for TargetCo",
            summary="Competing bid expected within days.",
            event_category="ma_corporate_action",
        )
        self.assertEqual(subtype, "Hostile Bid")
        self.assertEqual(severity, "High")

    def test_leadership_subtype_for_cause_termination(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Board says CEO terminated for cause after ethics probe",
            summary="Special committee investigation continues.",
            event_category="leadership_scandal",
        )
        self.assertEqual(subtype, "For-Cause Executive Termination")
        self.assertEqual(severity, "High")

    def test_positive_earnings_subtype_guidance_raise(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="SoftwareCo raises guidance after record revenue quarter",
            summary="Results came in above consensus with margin expansion.",
            event_category="positive_earnings_catalyst",
        )
        self.assertEqual(subtype, "Guidance Raise")
        self.assertEqual(severity, "High")

    def test_cybersecurity_distress_recovery_offsets(self):
        high_risk = self.app._financial_distress_assessment(
            title="Ransomware attack causes operations disrupted at Acme",
            summary="Material cybersecurity incident with exfiltration concerns.",
            event_category="cybersecurity",
        )
        mitigated = self.app._financial_distress_assessment(
            title="Acme reports services restored after ransomware incident",
            summary="Company says no evidence of exfiltration and no customer data accessed.",
            event_category="cybersecurity",
        )
        self.assertGreater(high_risk["score"], mitigated["score"])

    def test_clinical_distress_positive_offsets(self):
        downside = self.app._financial_distress_assessment(
            title="BiotechCo missed primary endpoint in phase 3 trial",
            summary="Program now faces delay risk.",
            event_category="clinical_regulatory_binary",
        )
        upside = self.app._financial_distress_assessment(
            title="BiotechCo receives FDA approval with priority review history",
            summary="Company previously earned breakthrough therapy designation.",
            event_category="clinical_regulatory_binary",
        )
        self.assertGreater(downside["score"], upside["score"])

    def test_fraud_distress_settlement_offsets(self):
        severe = self.app._financial_distress_assessment(
            title="GrandCo CFO indicted on wire fraud and securities fraud counts",
            summary="Department of Justice announces criminal charges after restatement.",
            event_category="fraud_accounting_enforcement",
        )
        milder = self.app._financial_distress_assessment(
            title="GrandCo settles with SEC without admitting or denying findings",
            summary="Terminated investigation with no findings of fraud; cooperation credit noted.",
            event_category="fraud_accounting_enforcement",
        )
        self.assertGreater(severe["score"], milder["score"])

    def test_supply_chain_distress_recovery_offsets(self):
        shock = self.app._financial_distress_assessment(
            title="ShipCo flags supplier bankruptcy and production halt",
            summary="Force majeure declared on key components.",
            event_category="supply_chain_disruption",
        )
        easing = self.app._financial_distress_assessment(
            title="ShipCo says it resumes production as shortage eases",
            summary="Alleviates shortage after new supplier agreement.",
            event_category="supply_chain_disruption",
        )
        self.assertGreater(shock["score"], easing["score"])

    def test_financial_distress_refinancing_offsets(self):
        severe = self.app._financial_distress_assessment(
            title="RetailCo files Chapter 11 after payment default",
            summary="Liquidity crisis and covenant default disclosed.",
            event_category="financial_distress",
        )
        mitigated = self.app._financial_distress_assessment(
            title="RetailCo says refinancing completed and covenant waiver received",
            summary="Liquidity improved after debt repaid with asset sale proceeds.",
            event_category="financial_distress",
        )
        self.assertGreater(severe["score"], mitigated["score"])

    def test_positive_earnings_distress_reduction(self):
        neutral = self.app._financial_distress_assessment(
            title="SoftCo reports quarterly update",
            summary="Operating trends are mixed.",
            event_category="positive_earnings_catalyst",
        )
        bullish = self.app._financial_distress_assessment(
            title="SoftCo raised guidance after beat estimates and record revenue",
            summary="Results were above consensus with margin expansion.",
            event_category="positive_earnings_catalyst",
        )
        self.assertGreater(neutral["score"], bullish["score"])


class ImpactTriageRegressionTests(unittest.TestCase):
    def setUp(self):
        self.triage = ImpactTriage({"triage": {"enabled": True, "agent_enabled": False}})

    def test_all_active_categories_generate_non_low_impact_for_clear_shocks(self):
        articles = [
            {
                "event_category": "cybersecurity",
                "title": "Material cybersecurity incident disclosed in SEC filing",
                "summary": "Operations disrupted after ransomware and supply chain attack.",
                "distress_score": 70,
            },
            {
                "event_category": "clinical_regulatory_binary",
                "title": "FDA issues complete response letter after trial miss",
                "summary": "Company did not meet endpoint and faces delay.",
                "distress_score": 70,
            },
            {
                "event_category": "product_safety_recall",
                "title": "Class I recall announced with stop-sale notice",
                "summary": "Serious injury reports and warning letter disclosed.",
                "distress_score": 70,
            },
            {
                "event_category": "fraud_accounting_enforcement",
                "title": "SEC charges issuer with securities fraud after restatement",
                "summary": "Material weakness and internal control failures cited in civil complaint.",
                "distress_score": 70,
            },
            {
                "event_category": "supply_chain_disruption",
                "title": "Manufacturer discloses plant shutdown amid chip shortage",
                "summary": "Supply chain disruption may delay shipments for two quarters.",
                "distress_score": 70,
            },
            {
                "event_category": "financial_distress",
                "title": "Issuer files Chapter 11 after covenant default",
                "summary": "Going-concern warning and liquidity crisis disclosed.",
                "distress_score": 80,
            },
            {
                "event_category": "dilutive_financing",
                "title": "Biotech prices registered direct offering with warrants",
                "summary": "Capital raise priced at discount with convertible notes option.",
                "distress_score": 65,
            },
            {
                "event_category": "ma_corporate_action",
                "title": "Hostile bid launched as DOJ sues to block prior merger",
                "summary": "Competing bid process introduces transaction volatility.",
                "distress_score": 68,
            },
            {
                "event_category": "leadership_scandal",
                "title": "CEO terminated for cause after board investigation",
                "summary": "Whistleblower complaint alleges executive misconduct.",
                "distress_score": 66,
            },
            {
                "event_category": "positive_earnings_catalyst",
                "title": "Chipmaker raises guidance after record revenue beat",
                "summary": "Margin expansion and above-consensus results announced.",
                "distress_score": 45,
            },
        ]

        for article in articles:
            result = self.triage.evaluate(article)
            self.assertIn(result["impact_likelihood"], {"MEDIUM", "HIGH"})
            self.assertGreaterEqual(result["impact_score"], 50)


class ConfigParityRegressionTests(unittest.TestCase):
    def test_active_categories_have_keyword_depth_and_distress_gate(self):
        cfg_path = REPO_ROOT / "config" / "settings.json"
        with cfg_path.open("r", encoding="utf-8") as f:
            cfg = json.load(f)

        active = [
            "cybersecurity",
            "clinical_regulatory_binary",
            "product_safety_recall",
            "fraud_accounting_enforcement",
            "supply_chain_disruption",
            "financial_distress",
            "dilutive_financing",
            "ma_corporate_action",
            "leadership_scandal",
            "positive_earnings_catalyst",
        ]
        categories = cfg.get("event_categories", {})
        gates = cfg.get("distress_model", {}).get("min_score_for_watch_by_category", {})

        for category in active:
            category_cfg = categories.get(category, {})
            self.assertTrue(category_cfg.get("enabled"), f"{category} must be enabled")
            self.assertGreaterEqual(
                len(category_cfg.get("keywords", [])),
                20,
                f"{category} should keep meaningful keyword depth",
            )
            self.assertIn(category, gates, f"{category} should have an explicit distress gate")


if __name__ == "__main__":
    unittest.main()
