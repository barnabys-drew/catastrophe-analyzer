import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from database_manager import DatabaseManager  # noqa: E402
from main import CatastropheAnalyzerApp  # noqa: E402


class _FakeDb:
    def __init__(self, *, triage_rows=None):
        self.saved_signals = []
        self.saved_analyses = []
        self.marked_signal_created = []
        self.marked_checked = []
        self._triage_rows = triage_rows or []

    def get_active_watches(self, max_days=7):
        return [
            {
                "ticker": "ACME",
                "company": "Acme Corp",
                "event_date": "2026-04-10",
                "event_category": "cybersecurity",
                "event_subtype": "Material Cyber Disclosure",
                "distress_score": "84",
                "status": "ACTIVE",
            }
        ]

    def get_signals(self):
        return []

    def get_analysis_history(self):
        return []

    def get_triage_events_for_keys(self, event_keys):
        return list(self._triage_rows)

    def add_analysis(self, analysis):
        self.saved_analyses.append(analysis)
        return True

    def add_signal(self, signal):
        self.saved_signals.append(signal)
        return True

    def mark_watch_signal_created(self, ticker, event_date):
        self.marked_signal_created.append((ticker, event_date))

    def mark_watch_last_checked(self, ticker, event_date):
        self.marked_checked.append((ticker, event_date))

    def mark_watch_expired(self, ticker, event_date):
        return True


class _FakeStockAnalyzer:
    @staticmethod
    def batch_analyze(requests):
        return [
            {
                "ticker": "ACME",
                "event_date": "2026-04-10",
                "event_category": "cybersecurity",
            }
        ]


class _FakeSignalGenerator:
    def __init__(self):
        self.signal_config = {"min_confidence_for_signal": 0.7}

    @staticmethod
    def generate_signals_batch(analyses):
        return [
            {
                "ticker": "ACME",
                "event_date": "2026-04-10",
                "event_category": "cybersecurity",
                "signal_type": "BUY",
                "confidence": 88.0,
            }
        ]

    @staticmethod
    def rank_signals(signals):
        return signals

    @staticmethod
    def filter_signals(signals, min_confidence=0.7):
        return signals


class RuntimeSignalReliabilityTests(unittest.TestCase):
    def test_triage_keyed_fetch_returns_only_requested_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = DatabaseManager(data_dir=tmp)
            db.upsert_triage_event(
                {
                    "ticker": "AAA",
                    "company": "A Co",
                    "event_date": "2026-04-10",
                    "event_category": "cybersecurity",
                    "event_subtype": "Material Cyber Disclosure",
                }
            )
            db.upsert_triage_event(
                {
                    "ticker": "BBB",
                    "company": "B Co",
                    "event_date": "2026-04-10",
                    "event_category": "financial_distress",
                    "event_subtype": "Chapter 11 Restructuring",
                }
            )
            rows = db.get_triage_events_for_keys(
                [("BBB", "2026-04-10", "financial_distress")]
            )
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["ticker"], "BBB")

    def test_missing_triage_does_not_use_confidence_as_impact_proxy(self):
        app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
        app.settings = {
            "event_watch": {"max_days": 7},
            "triage": {
                "min_impact_score_for_signal": 75,
                "min_distress_score_for_signal": 60,
            },
        }
        app.db = _FakeDb()
        app.stock_analyzer = _FakeStockAnalyzer()
        app.signal_generator = _FakeSignalGenerator()

        summary = app.update_watches_and_generate_signals(quiet=True)
        self.assertEqual(summary["signals_generated_raw"], 1)
        self.assertEqual(summary["signals_after_confidence_gate"], 1)
        self.assertEqual(summary["signals_after_triage_gate"], 0)
        self.assertEqual(summary["signals_saved"], 0)
        self.assertEqual(summary["signals_generated"], 0)

    def test_signal_passes_when_triage_impact_and_distress_are_present(self):
        app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
        app.settings = {
            "event_watch": {"max_days": 7},
            "triage": {
                "min_impact_score_for_signal": 75,
                "min_distress_score_for_signal": 60,
            },
        }
        app.db = _FakeDb(
            triage_rows=[
                {
                    "ticker": "ACME",
                    "event_date": "2026-04-10",
                    "event_category": "cybersecurity",
                    "impact_score": 82,
                    "distress_score": 68,
                    "event_subtype": "Material Cyber Disclosure",
                    "impact_summary": "Material customer-impact outage.",
                }
            ]
        )
        app.stock_analyzer = _FakeStockAnalyzer()
        app.signal_generator = _FakeSignalGenerator()

        summary = app.update_watches_and_generate_signals(quiet=True)
        self.assertEqual(summary["signals_after_triage_gate"], 1)
        self.assertEqual(summary["signals_saved"], 1)
        self.assertEqual(summary["signals_generated"], 1)


if __name__ == "__main__":
    unittest.main()
