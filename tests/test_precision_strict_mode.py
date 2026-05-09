import json
import importlib.util
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database_manager import DatabaseManager  # noqa: E402


def _load_real_class(module_filename: str, class_name: str):
    module_path = SRC_DIR / module_filename
    module_name = f"precision_{module_filename.replace('.py', '')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return getattr(module, class_name)


def _install_main_import_stubs() -> None:
    module_to_class = {
        "news_scraper": "NewsScraper",
        "entity_extractor": "EntityExtractor",
    }
    for module_name, class_name in module_to_class.items():
        mod = types.ModuleType(module_name)

        class _Stub:
            def __init__(self, *args, **kwargs):
                pass

        setattr(mod, class_name, _Stub)
        sys.modules[module_name] = mod


_install_main_import_stubs()
from main import CatastropheAnalyzerApp  # noqa: E402


class SignalGeneratorStrictTests(unittest.TestCase):
    def test_requires_event_drop_for_signal_generation(self):
        SignalGenerator = _load_real_class("signal_generator.py", "SignalGenerator")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "signals": {
                            "rsi_oversold_threshold": 28,
                            "price_drop_threshold": 15,
                            "volume_spike_threshold": 2.0,
                            "recovery_days_threshold": 5,
                            "confidence_levels": {"high": 0.85, "medium": 0.65, "low": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
            )
            generator = SignalGenerator(config_path=str(cfg_path))
            signal = generator.generate_buy_signal(
                {
                    "ticker": "TEST",
                    "event_date": "2026-03-25",
                    "event_category": "cybersecurity",
                    "current_price": 90.0,
                    "pre_event_price": 100.0,
                    "min_price_post_event": 88.0,
                    "max_drop_pct": 12.0,
                    "recovery_days": None,
                    "event_rsi": 24.0,
                    "rsi_oversold": True,
                    "price_below_ma20": True,
                    "volume_spike_at_event": 2.6,
                }
            )
            self.assertIsNone(signal, "Drop below strict threshold should block signal")

    def test_confidence_levels_are_config_driven(self):
        SignalGenerator = _load_real_class("signal_generator.py", "SignalGenerator")
        generator = SignalGenerator()
        generator.signal_config = {
            "confidence_levels": {"high": 0.9, "medium": 0.7, "low": 0.4}
        }
        self.assertEqual(generator._get_confidence_level(95), "HIGH")
        self.assertEqual(generator._get_confidence_level(75), "MEDIUM")
        self.assertEqual(generator._get_confidence_level(60), "LOW")

    def test_requires_48h_drop_filter_for_signal(self):
        SignalGenerator = _load_real_class("signal_generator.py", "SignalGenerator")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "signals": {
                            "rsi_oversold_threshold": 28,
                            "price_drop_threshold": 15,
                            "require_drop_within_48h": True,
                            "drop_within_48h_threshold": 2.0,
                            "volume_spike_threshold": 2.0,
                            "recovery_days_threshold": 5,
                            "confidence_levels": {"high": 0.85, "medium": 0.65, "low": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
            )
            generator = SignalGenerator(config_path=str(cfg_path))
            signal = generator.generate_buy_signal(
                {
                    "ticker": "TEST",
                    "event_date": "2026-03-25",
                    "event_category": "cybersecurity",
                    "current_price": 90.0,
                    "pre_event_price": 100.0,
                    "min_price_post_event": 80.0,
                    "max_drop_pct": 20.0,
                    "drop_48h_pct": 0.6,
                    "recovery_days": None,
                    "event_rsi": 24.0,
                    "rsi_oversold": True,
                    "price_below_ma20": True,
                    "volume_spike_at_event": 2.6,
                }
            )
            self.assertIsNone(signal, "Insufficient 48h drop should block signal")

    def test_category_specific_thresholds_override_global(self):
        SignalGenerator = _load_real_class("signal_generator.py", "SignalGenerator")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "signals": {
                            "rsi_oversold_threshold": 28,
                            "price_drop_threshold": 20,
                            "require_drop_within_48h": True,
                            "drop_within_48h_threshold": 2.0,
                            "volume_spike_threshold": 2.0,
                            "recovery_days_threshold": 5,
                            "by_category": {
                                "clinical_regulatory_binary": {
                                    "price_drop_threshold": 10,
                                    "drop_within_48h_threshold": 0.5,
                                    "volume_spike_threshold": 1.5,
                                }
                            },
                            "confidence_levels": {"high": 0.85, "medium": 0.65, "low": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
            )
            generator = SignalGenerator(config_path=str(cfg_path))
            analysis = {
                "ticker": "CLIN",
                "event_date": "2026-03-25",
                "event_category": "clinical_regulatory_binary",
                "current_price": 90.0,
                "pre_event_price": 100.0,
                "min_price_post_event": 89.0,
                "max_drop_pct": 12.0,
                "drop_48h_pct": 0.8,
                "recovery_days": None,
                "event_rsi": 24.0,
                "rsi_oversold": True,
                "price_below_ma20": True,
                "volume_spike_at_event": 1.7,
            }
            signal = generator.generate_buy_signal(analysis)
            self.assertIsNotNone(signal, "Category-specific thresholds should allow signal")

    def test_liquidity_filter_rejects_and_reports_reason(self):
        SignalGenerator = _load_real_class("signal_generator.py", "SignalGenerator")
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "signals": {
                            "rsi_oversold_threshold": 28,
                            "price_drop_threshold": 15,
                            "require_drop_within_48h": True,
                            "drop_within_48h_threshold": 2.0,
                            "volume_spike_threshold": 2.0,
                            "recovery_days_threshold": 5,
                            "min_price_for_signal": 2.5,
                            "min_avg_volume_for_signal": 500000,
                            "confidence_levels": {"high": 0.85, "medium": 0.65, "low": 0.4},
                        }
                    }
                ),
                encoding="utf-8",
            )
            generator = SignalGenerator(config_path=str(cfg_path))
            analyses = [
                {
                    "ticker": "THIN",
                    "event_date": "2026-03-25",
                    "event_category": "cybersecurity",
                    "current_price": 6.0,
                    "avg_volume_20d": 120000,
                    "pre_event_price": 10.0,
                    "min_price_post_event": 7.5,
                    "max_drop_pct": 20.0,
                    "drop_48h_pct": 3.0,
                    "recovery_days": None,
                    "event_rsi": 24.0,
                    "rsi_oversold": True,
                    "price_below_ma20": True,
                    "volume_spike_at_event": 2.8,
                }
            ]
            signals, diagnostics = generator.generate_signals_with_diagnostics(analyses)
            self.assertEqual(signals, [])
            diag = diagnostics.get(("THIN", "2026-03-25", "cybersecurity"), {})
            self.assertEqual(diag.get("decision"), "RULE_REJECTED")
            self.assertIn("liquidity_volume_floor_failed", diag.get("reason", ""))


class StockAnalyzerEventTimingTests(unittest.TestCase):
    def test_event_rsi_is_used_for_oversold_flag(self):
        StockAnalyzer = _load_real_class("stock_analyzer.py", "StockAnalyzer")
        analyzer = StockAnalyzer(use_mock=True)
        start = datetime(2026, 1, 1)
        dates = [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(40)]
        # Deep selloff into event period, then rebound later.
        prices = [100 - i * 1.5 for i in range(20)] + [70 + i * 1.4 for i in range(20)]
        volumes = [1_000_000] * 40
        volumes[15] = 4_000_000

        analyzer.get_price_history = lambda ticker, days=90: {
            "ticker": ticker,
            "prices": prices,
            "volumes": volumes,
            "dates": dates,
            "high": max(prices),
            "low": min(prices),
            "close": prices[-1],
            "volume": volumes[-1],
        }

        result = analyzer.analyze_event_impact("TEST", "2026-01-16", "cybersecurity")
        self.assertIn("event_rsi", result)
        self.assertLessEqual(result["event_rsi"], result["current_rsi"])
        self.assertEqual(result["rsi_oversold"], result["event_rsi"] < 30)
        self.assertIn("drop_48h_pct", result)
        self.assertGreaterEqual(result["drop_48h_pct"], 0.0)
        self.assertEqual(result.get("post_event_window_days"), 2)


class MainSignalTriageGateTests(unittest.TestCase):
    class _FakeSignalGenerator:
        def __init__(self):
            self.signal_config = {"min_confidence_for_signal": 0.0}

        def generate_signals_batch(self, analyses):
            out = []
            for a in analyses:
                out.append(
                    {
                        "ticker": a["ticker"],
                        "signal_type": "BUY_OPPORTUNITY",
                        "event_date": a["event_date"],
                        "event_category": a["event_category"],
                        "confidence": 95,
                        "confidence_level": "HIGH",
                        "suggested_entry": 90.0,
                        "suggested_stop_loss": 84.0,
                        "risk_reward": {"target_price": 102.0, "risk_reward_ratio": 2.0},
                        "reasons": ["strict-mode test"],
                    }
                )
            return out

        def rank_signals(self, signals):
            return signals

        def filter_signals(self, signals, min_confidence=0.0):
            return signals

        def generate_signals_with_diagnostics(self, analyses):
            signals = self.generate_signals_batch(analyses)
            diagnostics = {}
            for s in signals:
                key = (
                    s.get("ticker", ""),
                    s.get("event_date", s.get("breach_date", "")),
                    s.get("event_category", ""),
                )
                diagnostics[key] = {
                    "decision": "RULE_PASSED",
                    "reason": "rule_passed",
                    "confidence": s.get("confidence", ""),
                }
            return signals, diagnostics

    class _FakeStockAnalyzer:
        def batch_analyze(self, requests, event_date=None, breach_date=None):
            rows = []
            for r in requests:
                rows.append(
                    {
                        "ticker": r["ticker"],
                        "event_date": r["event_date"],
                        "event_category": r["event_category"],
                        "pre_event_price": 100.0,
                        "current_price": 90.0,
                        "min_price_post_event": 85.0,
                        "max_drop_pct": 15.0,
                        "recovery_days": None,
                        "current_rsi": 29.0,
                        "event_rsi": 27.0,
                        "rsi_oversold": True,
                        "price_below_ma20": True,
                        "volume_spike_at_event": 2.4,
                    }
                )
            return rows

    def test_triage_thresholds_gate_signal_persistence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(data_dir=tmpdir)
            event_day = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d")
            db.add_watch_if_new(
                {
                    "ticker": "PASS",
                    "company": "Passing Co",
                    "event_date": event_day,
                    "event_category": "cybersecurity",
                    "status": "ACTIVE",
                }
            )
            db.add_watch_if_new(
                {
                    "ticker": "FAIL",
                    "company": "Failing Co",
                    "event_date": event_day,
                    "event_category": "cybersecurity",
                    "status": "ACTIVE",
                }
            )
            db.upsert_triage_event(
                {
                    "event_key": "pass-key",
                    "ticker": "PASS",
                    "company": "Passing Co",
                    "event_date": event_day,
                    "event_category": "cybersecurity",
                    "event_subtype": "Ransomware",
                    "distress_score": 70,
                    "distress_likelihood": "HIGH",
                    "impact_score": 80,
                    "impact_likelihood": "HIGH",
                    "impact_summary": "Passing triage row.",
                    "title": "Passing article",
                    "url": "https://example.com/pass",
                }
            )
            db.upsert_triage_event(
                {
                    "event_key": "fail-key",
                    "ticker": "FAIL",
                    "company": "Failing Co",
                    "event_date": event_day,
                    "event_category": "cybersecurity",
                    "event_subtype": "Ransomware",
                    "distress_score": 45,
                    "distress_likelihood": "MEDIUM",
                    "impact_score": 55,
                    "impact_likelihood": "MEDIUM",
                    "impact_summary": "Failing triage row.",
                    "title": "Failing article",
                    "url": "https://example.com/fail",
                }
            )

            app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
            app.db = db
            app.signal_generator = self._FakeSignalGenerator()
            app.stock_analyzer = self._FakeStockAnalyzer()
            app.settings = {
                "event_watch": {"max_days": 7},
                "triage": {
                    "min_impact_score_for_alert": 60,
                    "min_distress_score_for_alert": 35,
                    "min_impact_score_for_signal": 75,
                    "min_distress_score_for_signal": 60,
                },
            }

            summary = app.update_watches_and_generate_signals(quiet=True)
            self.assertEqual(summary["signals_saved"], 1)
            self.assertEqual(len(summary["new_signals"]), 1)
            self.assertEqual(summary["new_signals"][0]["ticker"], "PASS")
            persisted = db.get_signals()
            self.assertEqual(len(persisted), 1)
            self.assertEqual(persisted[0]["ticker"], "PASS")


class MainEntityValidationGateTests(unittest.TestCase):
    class _FakeNewsScraper:
        keywords_by_category: dict = {}  # main.py:1777 reads this on enriched articles

        def scrape_all_sources(self):
            return [
                {
                    "title": "Urgent recall issued for beans over contamination risk",
                    "summary": "",
                    "link": "https://example.com/urgent-beans",
                    "source": "test",
                    "published": "Sun, 29 Mar 2026 10:00:00 GMT",
                    "event_category": "product_safety_recall",
                }
            ]

        def filter_recent_articles(self, rows, hours_back):
            return rows

        def enrich_articles_with_body(self, articles, max_fetches=30, fetch_delay_seconds=0.5):
            return articles

    class _FakeEntityExtractor:
        def batch_extract(self, rows):
            return [
                {
                    **rows[0],
                    "mapped_candidates": [{"company": "Urgent", "ticker": "ULY"}],
                    "mapped_entities": [],
                    "rejected_entities": [
                        {
                            "company": "Urgent",
                            "ticker": "ULY",
                            "validation_status": "rejected",
                            "validation_reason": "agent endpoint not configured",
                            "validation_engine": "agent_unavailable",
                        }
                    ],
                    "has_publicly_traded": False,
                }
            ]

    class _FakeImpactTriage:
        def evaluate(self, payload):
            return {"impact_score": 80, "impact_likelihood": "HIGH", "impact_summary": "test"}

    class _FakeStockAnalyzer:
        def get_event_price_series(self, ticker, event_date, pre_days=30, post_days=30):
            return []

    def test_fail_closed_rejection_skips_watch_creation(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = DatabaseManager(data_dir=tmpdir)
            app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
            app.db = db
            app.news_scraper = self._FakeNewsScraper()
            app.entity_extractor = self._FakeEntityExtractor()
            app.impact_triage = self._FakeImpactTriage()
            app.stock_analyzer = self._FakeStockAnalyzer()
            app.settings = {
                "scraping": {"hours_back": 24},
                "price_series": {"pre_days": 30, "post_days": 30},
                "distress_model": {"min_score_for_watch_default": 0},
            }
            app._classify_event_subtype_and_severity = lambda **kwargs: ("Recall", "High")
            app._financial_distress_assessment = lambda **kwargs: {"likelihood": "HIGH", "score": 80}
            app._distress_gate_min_score = lambda event_category: 0
            app._triage_thresholds = lambda: (60, 35)

            summary = app.detect_new_events(quiet=True)
            self.assertEqual(summary["watches_created"], 0)
            self.assertEqual(summary["skipped_unapproved_validation"], 1)
            self.assertEqual(db.get_active_watches(max_days=7), [])


if __name__ == "__main__":
    unittest.main()
