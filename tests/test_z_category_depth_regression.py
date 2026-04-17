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
        if module_name == "signal_generator":
            setattr(mod, "compute_signal_rank_score", lambda signal: 0.0)
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

    def test_sanctions_subtype_ofac_designation(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="OFAC adds ChipMaker to SDN list after export control review",
            summary="Treasury Department designates entity under sanctions program.",
            event_category="geopolitical_sanctions_exposure",
        )
        self.assertEqual(subtype, "OFAC Designation")
        self.assertEqual(severity, "High")

    def test_negative_earnings_subtype_guidance_cut(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="RetailCo issues profit warning and cuts guidance for full year",
            summary="Lowered outlook reflects weaker than expected consumer demand.",
            event_category="negative_earnings_catalyst",
        )
        self.assertEqual(subtype, "Profit / Revenue Warning")
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

    def test_sanctions_distress_waiver_offsets(self):
        severe = self.app._financial_distress_assessment(
            title="OFAC designates TechCo on entity list after sanctions violation",
            summary="Asset freeze imposed and export ban in effect.",
            event_category="geopolitical_sanctions_exposure",
        )
        mitigated = self.app._financial_distress_assessment(
            title="TechCo receives license granted after sanctions review",
            summary="Sanctions lifted and entity delisted from entity list.",
            event_category="geopolitical_sanctions_exposure",
        )
        self.assertGreater(severe["score"], mitigated["score"])

    def test_negative_earnings_distress_vs_recovery(self):
        severe = self.app._financial_distress_assessment(
            title="IndustrialCo issues profit warning after guidance cut and revenue miss",
            summary="Lowered guidance reflects weaker than expected demand and margin compression.",
            event_category="negative_earnings_catalyst",
        )
        softer = self.app._financial_distress_assessment(
            title="IndustrialCo reports one-time charge but reaffirmed guidance",
            summary="Non-recurring items drove shortfall; expects recovery in next quarter.",
            event_category="negative_earnings_catalyst",
        )
        self.assertGreater(severe["score"], softer["score"])

    # ---- Wave 1 / Wave 2 / Wave 3 regression tests ----

    def test_short_seller_report_subtype(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Hindenburg Research publishes short report alleging fabricated revenue",
            summary="Activist short piece alleges channel stuffing and undisclosed related party transactions.",
            event_category="short_seller_report",
        )
        self.assertEqual(subtype, "Hindenburg Short Report")
        self.assertEqual(severity, "High")

    def test_short_seller_report_distress_vs_rebuttal(self):
        severe = self.app._financial_distress_assessment(
            title="Hindenburg Research alleges fabricated revenue and channel stuffing",
            summary="Activist short report claims undisclosed related party transactions.",
            event_category="short_seller_report",
        )
        mitigated = self.app._financial_distress_assessment(
            title="Company denies short seller report and announces independent review",
            summary="Rebuttal issued after Hindenburg allegations; independent review to proceed.",
            event_category="short_seller_report",
        )
        self.assertGreater(severe["score"], mitigated["score"])

    def test_credit_rating_subtype_fallen_angel(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="S&P downgrades issuer to junk; cut to junk triggers fallen angel status",
            summary="Speculative grade rating assigned after default risk elevated.",
            event_category="credit_rating_action",
        )
        self.assertEqual(subtype, "Fallen Angel Downgrade")
        self.assertEqual(severity, "High")

    def test_going_concern_subtype_substantial_doubt(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Auditor cites substantial doubt about going concern",
            summary="10-K filing includes going concern warning from auditor.",
            event_category="going_concern_auditor_change",
        )
        self.assertEqual(subtype, "Going Concern Warning")
        self.assertEqual(severity, "High")

    def test_guidance_cut_preannouncement_subtype_withdrawal(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Company withdraws guidance and suspends full-year outlook",
            summary="Business update filing includes guidance withdrawal and reset expectations.",
            event_category="guidance_cut_preannouncement",
        )
        self.assertEqual(subtype, "Guidance Withdrawal")
        self.assertEqual(severity, "High")

    def test_activist_13d_subtype_proxy_fight(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Elliott Management launches proxy fight at TargetCo",
            summary="Activist campaign includes schedule 13D filing and director nominations.",
            event_category="activist_13d_filing",
        )
        self.assertEqual(subtype, "Proxy Contest")
        self.assertEqual(severity, "High")

    def test_labor_action_subtype_prolonged_strike(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Union declares prolonged strike and work stoppage at three plants",
            summary="Prolonged strike extends across multiple facilities with indefinite strike vote.",
            event_category="labor_action",
        )
        self.assertEqual(subtype, "Prolonged Strike")
        self.assertEqual(severity, "High")

    def test_securities_class_action_subtype_dismissal_denied(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Judge denies motion to dismiss in securities class action lawsuit",
            summary="Motion to dismiss denied; lead plaintiff deadline set.",
            event_category="securities_class_action",
        )
        self.assertEqual(subtype, "Dismissal Denied")
        self.assertEqual(severity, "High")

    def test_insider_trading_cluster_subtype(self):
        subtype, severity = self.app._classify_event_subtype_and_severity(
            title="Cluster of insider sales: C-suite selling accelerates before results",
            summary="Multiple officers sell shares in a concentrated cluster of insider sales.",
            event_category="insider_trading_cluster",
        )
        self.assertEqual(subtype, "Insider Selling Cluster")
        self.assertEqual(severity, "High")


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
            {
                "event_category": "geopolitical_sanctions_exposure",
                "title": "OFAC adds manufacturer to entity list after export ban review",
                "summary": "Asset freeze and sanctions violation penalties expected.",
                "distress_score": 70,
            },
            {
                "event_category": "negative_earnings_catalyst",
                "title": "Retailer issues profit warning after guidance cut",
                "summary": "Revenue warning reflects negative preannouncement and margin compression.",
                "distress_score": 65,
            },
            {
                "event_category": "short_seller_report",
                "title": "Hindenburg Research publishes short report on issuer",
                "summary": "Activist short piece alleges fabricated revenue and channel stuffing.",
                "distress_score": 70,
            },
            {
                "event_category": "credit_rating_action",
                "title": "Moody's downgrades issuer; cut to junk and negative outlook",
                "summary": "Fallen angel downgrade cites default risk elevated; speculative grade assigned.",
                "distress_score": 65,
            },
            {
                "event_category": "going_concern_auditor_change",
                "title": "Auditor flags substantial doubt about going concern",
                "summary": "Non-reliance on previously issued financials disclosed under item 4.02.",
                "distress_score": 72,
            },
            {
                "event_category": "guidance_cut_preannouncement",
                "title": "Company withdraws guidance and suspends full-year outlook",
                "summary": "Business update preannounces worse-than-expected quarter; reset expectations.",
                "distress_score": 62,
            },
            {
                "event_category": "labor_action",
                "title": "Nationwide strike expands; work stoppage enters third week",
                "summary": "Prolonged strike and lockout extend disruption; UAW strike widens.",
                "distress_score": 60,
            },
            {
                "event_category": "securities_class_action",
                "title": "Court denies motion to dismiss in securities fraud lawsuit",
                "summary": "Class certification granted; lead plaintiff deadline set.",
                "distress_score": 55,
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
            "geopolitical_sanctions_exposure",
            "negative_earnings_catalyst",
            "short_seller_report",
            "credit_rating_action",
            "going_concern_auditor_change",
            "guidance_cut_preannouncement",
            "activist_13d_filing",
            "labor_action",
            "securities_class_action",
            "insider_trading_cluster",
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
