import sys
import unittest
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main import CatastropheAnalyzerApp  # noqa: E402


def _load_real_class(module_filename: str, class_name: str):
    module_path = SRC_DIR / module_filename
    module_name = f"freshness_{module_filename.replace('.py', '')}"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return getattr(module, class_name)


class _FakeTriageDb:
    def __init__(self, rows):
        self._rows = rows

    def get_triage_events(self, alert_state=None, min_impact_score=None, min_distress_score=None):
        out = []
        for row in self._rows:
            if alert_state and str(row.get("alert_state", "")).upper() != str(alert_state).upper():
                continue
            impact = int(float(str(row.get("impact_score", 0))))
            distress = int(float(str(row.get("distress_score", 0))))
            if min_impact_score is not None and impact < int(min_impact_score):
                continue
            if min_distress_score is not None and distress < int(min_distress_score):
                continue
            out.append(dict(row))
        return out


class AlertCooldownTests(unittest.TestCase):
    def test_recent_attempts_are_suppressed_from_new_alert_batch(self):
        now = datetime.now(timezone.utc)
        recent = (now - timedelta(hours=2)).isoformat()
        old = (now - timedelta(hours=9)).isoformat()
        rows = [
            {
                "event_key": "recent",
                "ticker": "AAA",
                "event_date": "2026-04-15",
                "event_category": "cybersecurity",
                "impact_score": 90,
                "distress_score": 80,
                "alert_state": "NEW",
                "last_alerted_at": recent,
            },
            {
                "event_key": "old",
                "ticker": "BBB",
                "event_date": "2026-04-15",
                "event_category": "cybersecurity",
                "impact_score": 90,
                "distress_score": 80,
                "alert_state": "NEW",
                "last_alerted_at": old,
            },
            {
                "event_key": "never",
                "ticker": "CCC",
                "event_date": "2026-04-15",
                "event_category": "cybersecurity",
                "impact_score": 90,
                "distress_score": 80,
                "alert_state": "NEW",
                "last_alerted_at": "",
            },
        ]
        app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
        app.settings = {
            "triage": {
                "min_impact_score_for_alert": 60,
                "min_distress_score_for_alert": 35,
                "duplicate_alert_suppression_hours": 6,
            }
        }
        app.db = _FakeTriageDb(rows)

        candidates = app._high_value_events_ready_for_alert()
        keys = {row.get("event_key") for row in candidates}
        self.assertEqual(keys, {"old", "never"})


class ScraperFreshnessGuardrailTests(unittest.TestCase):
    def _settings(self, drop_unparseable: bool):
        return {
            "event_categories": {
                "cybersecurity": {"enabled": True, "keywords": ["breach"]},
            },
            "news_sources": {
                "dummy": {
                    "enabled": True,
                    "url": "https://example.com/feed",
                    "event_category": "cybersecurity",
                }
            },
            "scraping": {
                "timeout": 10,
                "max_results_per_source": 10,
                "hours_back": 24,
                "drop_unparseable_published": drop_unparseable,
                "max_article_age_hours": 24,
            },
        }

    def test_unparseable_published_is_dropped_when_enabled(self):
        NewsScraper = _load_real_class("news_scraper.py", "NewsScraper")
        scraper = NewsScraper(settings=self._settings(drop_unparseable=True))
        rows = [{"title": "x", "summary": "x", "published": "not-a-date"}]
        self.assertEqual(scraper.filter_recent_articles(rows, hours=24), [])

    def test_unparseable_published_can_be_kept_when_disabled(self):
        NewsScraper = _load_real_class("news_scraper.py", "NewsScraper")
        scraper = NewsScraper(settings=self._settings(drop_unparseable=False))
        rows = [{"title": "x", "summary": "x", "published": "not-a-date"}]
        self.assertEqual(len(scraper.filter_recent_articles(rows, hours=24)), 1)


if __name__ == "__main__":
    unittest.main()
