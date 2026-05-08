import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from config_loader import SettingsValidationError, validate_runtime_settings  # noqa: E402
from runtime_cycle import run_cycle_with_alerts  # noqa: E402


def _load_real_class(module_filename: str, class_name: str):
    module_path = SRC_DIR / module_filename
    module_name = f"runtime_guardrails_{module_filename.replace('.py', '')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class ConfigValidationTests(unittest.TestCase):
    def test_production_settings_file_passes_runtime_validation(self):
        cfg_path = REPO_ROOT / "config" / "settings.json"
        with cfg_path.open("r", encoding="utf-8") as f:
            settings = json.load(f)
        validate_runtime_settings(settings)

    def test_invalid_runtime_settings_fail_fast(self):
        bad = {
            "event_categories": {"cybersecurity": {"enabled": True, "keywords": ["breach"]}},
            "news_sources": {
                "test": {
                    "enabled": True,
                    "url": "https://example.com/feed",
                    "event_category": "cybersecurity",
                }
            },
            "scraping": {"timeout": 10, "max_results_per_source": 10, "hours_back": 24},
            "signals": {"confidence_levels": {"high": 0.9, "medium": 0.7, "low": 0.4}},
            "triage": {
                "min_impact_score_for_alert": 60,
                "min_distress_score_for_alert": 40,
                "min_impact_score_for_signal": 50,
                "min_distress_score_for_signal": 30,
            },
            "monitoring_schedule": {"scan_interval_minutes": 15},
            "distress_model": {"min_score_for_watch_default": 50},
        }
        with self.assertRaises(SettingsValidationError):
            validate_runtime_settings(bad)


class RuntimeDeliveryGuardrailTests(unittest.TestCase):
    class _FakeDb:
        def __init__(self):
            self.marked = []
            self.attempted = []

        def mark_triage_sent(self, event_keys):
            self.marked.extend(event_keys)
            return len(event_keys)

        def mark_triage_alert_attempted(self, event_keys):
            self.attempted.extend(event_keys)
            return len(event_keys)

        def display_category_yield_dashboard(self, days=30):
            return None

    class _FakeApp:
        def __init__(self, repo_root: str):
            self.repo_root = repo_root
            self.db = RuntimeDeliveryGuardrailTests._FakeDb()
            self.settings = {
                "dashboard_readiness": {
                    "enabled": True,
                    "window_days": 7,
                    "min_total_signals": 1,
                    "min_categories_with_signals": 1,
                    "min_event_to_signal_rate_pct": 0.0,
                    "min_analysis_to_signal_rate_pct": 0.0,
                    "required_consecutive_passes": 1,
                }
            }

        def run_one_cycle(self, quiet=False):
            return {
                "new_high_value_events": [
                    {"event_key": "evt-delivered", "ticker": "AAA"},
                    {"event_key": "evt-failed", "ticker": "BBB"},
                ],
                "new_signals": [{"ticker": "AAA"}],
                "dropoff_breakdown": {"watches_considered": 2, "signals_saved": 1},
                "dropoff_rates": {"watch_to_saved_rate_pct": 50.0},
                "gate_rejections_by_reason": {"triage_threshold_failed": 1},
                "category_gate_summary": {"cybersecurity": {"signals_saved": 1}},
            }

    class _FakeAlerts:
        @staticmethod
        def send_high_value_event_alerts(events, emit_console=True):
            return {
                "items_attempted": len(events),
                "items_delivered": 1,
                "event_results": [
                    {"event_key": "evt-delivered", "ticker": "AAA", "delivered": True, "delivery_results": []},
                    {"event_key": "evt-failed", "ticker": "BBB", "delivered": False, "delivery_results": []},
                ],
                "channels": {"email": {"attempted": 2, "success": 1, "failed": 1, "skipped": 0}},
            }

        @staticmethod
        def send_buy_signal_alerts(signals, emit_console=True):
            return {
                "items_attempted": len(signals),
                "items_delivered": 1,
                "channels": {"ntfy": {"attempted": 1, "success": 1, "failed": 0, "skipped": 0}},
            }

        @staticmethod
        def send_trading_advice(signals, emit_console=True):
            return {"kind": "trading_advice", "trades_generated": 0, "discord_posted": 0}

    def test_runtime_cycle_marks_only_confirmed_triage_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = self._FakeApp(repo_root=tmp)
            summary = run_cycle_with_alerts(app, self._FakeAlerts(), quiet=True)

            self.assertEqual(app.db.marked, ["evt-delivered"])
            self.assertEqual(app.db.attempted, ["evt-delivered", "evt-failed"])
            metrics = summary.get("runtime_metrics", {})
            self.assertEqual(metrics.get("high_value_events_detected"), 2)
            self.assertEqual(metrics.get("high_value_events_delivered"), 1)
            self.assertEqual(metrics.get("high_value_events_marked_sent"), 1)
            self.assertIn("dashboard_readiness", metrics)
            self.assertIn("dropoff_breakdown", metrics)

            snapshot_path = Path(tmp) / "data" / "signal_quality_weekly_snapshot.json"
            readiness_path = Path(tmp) / "data" / "dashboard_readiness_state.json"
            self.assertTrue(snapshot_path.exists())
            self.assertTrue(readiness_path.exists())


class ScraperRetryTests(unittest.TestCase):
    def _scraper_settings(self):
        return {
            "event_categories": {
                "cybersecurity": {
                    "enabled": True,
                    "keywords": ["breach"],
                }
            },
            "news_sources": {},
            "scraping": {
                "timeout": 10,
                "max_results_per_source": 5,
                "hours_back": 24,
                "retry_on_failure": True,
                "max_retries": 2,
                "retry_backoff_seconds": 0,
            },
        }

    def test_scraper_retries_then_recovers(self):
        NewsScraper = _load_real_class("news_scraper.py", "NewsScraper")
        scraper = NewsScraper(settings=self._scraper_settings())
        parse_calls = {"count": 0}

        def _parse(*args, **kwargs):
            parse_calls["count"] += 1
            if parse_calls["count"] == 1:
                raise RuntimeError("temporary rss failure")
            return SimpleNamespace(
                bozo=False,
                entries=[
                    {
                        "title": "Major breach disclosed",
                        "summary": "breach impacts systems",
                        "link": "https://example.com/breach",
                        "published": "Mon, 01 Jan 2026 00:00:00 GMT",
                    }
                ],
            )

        parser_module = NewsScraper.scrape_rss_feed.__globals__["feedparser"]
        with patch.object(parser_module, "parse", side_effect=_parse):
            rows = scraper.scrape_rss_feed(
                feed_url="https://example.com/feed.xml",
                source_name="test_source",
                event_category="cybersecurity",
                keywords=["breach"],
                max_entries=10,
            )

        self.assertEqual(parse_calls["count"], 2)
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
