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

        active = ["cybersecurity", "clinical_regulatory_binary", "product_safety_recall"]
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
