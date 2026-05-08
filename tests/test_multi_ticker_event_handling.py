import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from main import CatastropheAnalyzerApp  # noqa: E402


class _FakeNewsScraper:
    def __init__(self):
        self.keywords_by_category = {
            "product_safety_recall": ["recall", "contamination", "warning letter"],
        }
        self.breach_keywords = ["recall", "contamination"]

    @staticmethod
    def scrape_all_sources():
        return [{"title": "placeholder", "summary": "placeholder"}]

    @staticmethod
    def filter_recent_articles(raw_articles, hours_back):
        return raw_articles

    @staticmethod
    def enrich_articles_with_body(articles):
        return articles


class _FakeEntityExtractor:
    def __init__(self, entities):
        self._entities = entities

    def batch_extract(self, _recent_articles):
        return self._entities


class _FakeStockAnalyzer:
    def __init__(self, tradable_by_ticker):
        self._tradable = dict(tradable_by_ticker)

    def validate_tradable_ticker(self, ticker):
        return bool(self._tradable.get((ticker or "").upper(), False))

    @staticmethod
    def get_event_price_series(ticker, event_date, pre_days=30, post_days=30):
        return []


class _FakeImpactTriage:
    @staticmethod
    def evaluate(_payload):
        return {
            "impact_score": 82,
            "impact_likelihood": "HIGH",
            "impact_summary": "Mock impact summary",
            "triage_engine": "deterministic",
        }


class _FakeDb:
    def __init__(self, existing_event_keys=None, existing_watch_keys=None):
        self._existing_event_keys = set(existing_event_keys or [])
        self._watch_keys = set(existing_watch_keys or [])
        self.upserted_triage = []
        self.created_watches = []

    @staticmethod
    def build_event_key(ticker, event_date, event_category, source_url="", title=""):
        return f"{ticker}|{event_date}|{event_category}|{source_url}|{title}"

    def triage_event_exists_for_source_ticker(self, *, ticker, event_date, event_category, source_url="", title=""):
        key = self.build_event_key(ticker, event_date, event_category, source_url, title)
        return key in self._existing_event_keys

    def upsert_triage_event(self, triage_event):
        self.upserted_triage.append(dict(triage_event))
        key = triage_event.get("event_key", "")
        if key:
            self._existing_event_keys.add(key)
        return triage_event

    def add_watch_if_new(self, watch):
        key = (
            watch.get("ticker", ""),
            watch.get("event_date", ""),
            watch.get("event_category", ""),
        )
        if key in self._watch_keys:
            return False
        self._watch_keys.add(key)
        self.created_watches.append(dict(watch))
        return True

    @staticmethod
    def add_breach(_event):
        return True

    @staticmethod
    def add_price_timeseries(_rows):
        return True

    @staticmethod
    def mark_timeseries_saved(_ticker, _event_date):
        return True

    @staticmethod
    def update_watch_metadata(ticker, breach_date, company=None, source=None, url=None):
        return True

    def get_triage_events(self, alert_state=None, min_impact_score=None, min_distress_score=None):
        out = []
        for row in self.upserted_triage:
            if alert_state and (row.get("alert_state", "").upper() != str(alert_state).upper()):
                continue
            impact = int(row.get("impact_score", 0))
            distress = int(row.get("distress_score", 0))
            if min_impact_score is not None and impact < int(min_impact_score):
                continue
            if min_distress_score is not None and distress < int(min_distress_score):
                continue
            out.append(row)
        return out


def _build_multi_ticker_article():
    return {
        "title": "Eye drops recalled at Walgreens and Kroger over contamination risk",
        "summary": "Manufacturer issued warning letter follow-up for products sold at both retailers.",
        "published": "Sun, 29 Mar 2026 12:00:00 GMT",
        "source": "google_news_product_recall_recent",
        "link": "https://news.example.com/recall-story",
        "event_category": "product_safety_recall",
        "has_publicly_traded": True,
        "mapped_candidates": [
            {"company": "Walgreens", "ticker": "WBA"},
            {"company": "Kroger", "ticker": "KR"},
        ],
        "mapped_entities": [
            {
                "company": "Walgreens",
                "ticker": "WBA",
                "validation_status": "approved",
                "validation_reason": "approved by strict rules",
                "validation_confidence": 0.92,
                "validation_engine": "strict_rules",
            },
            {
                "company": "Kroger",
                "ticker": "KR",
                "validation_status": "approved",
                "validation_reason": "approved by strict rules",
                "validation_confidence": 0.90,
                "validation_engine": "strict_rules",
            },
        ],
    }


class MultiTickerEventHandlingTests(unittest.TestCase):
    @staticmethod
    def _make_app(db, entities, tradable_map):
        app = CatastropheAnalyzerApp.__new__(CatastropheAnalyzerApp)
        app.settings = {
            "scraping": {"hours_back": 24},
            "price_series": {"pre_days": 30, "post_days": 30},
            "distress_model": {
                "min_score_for_watch_default": 50,
                "min_score_for_watch_by_category": {"product_safety_recall": 50},
            },
            "triage": {"min_impact_score_for_alert": 60, "min_distress_score_for_alert": 35},
        }
        app.news_scraper = _FakeNewsScraper()
        app.entity_extractor = _FakeEntityExtractor(entities)
        app.stock_analyzer = _FakeStockAnalyzer(tradable_map)
        app.impact_triage = _FakeImpactTriage()
        app.db = db
        return app

    def test_multi_ticker_fanout_skips_untradable_primary(self):
        db = _FakeDb()
        entities = [_build_multi_ticker_article()]
        app = self._make_app(db=db, entities=entities, tradable_map={"WBA": False, "KR": True})

        summary = app.detect_new_events(quiet=True)

        self.assertEqual(summary["watches_created"], 1)
        self.assertEqual(summary["skipped_untradable_candidates"], 1)
        self.assertEqual(len(db.created_watches), 1)
        self.assertEqual(db.created_watches[0]["ticker"], "KR")
        self.assertEqual(len(db.upserted_triage), 1)
        self.assertEqual(db.upserted_triage[0]["ticker"], "KR")

    def test_source_ticker_dedupe_counter_tracked(self):
        article = _build_multi_ticker_article()
        existing_key = _FakeDb.build_event_key(
            "KR",
            "2026-03-29",
            "product_safety_recall",
            article.get("link", ""),
            article.get("title", ""),
        )
        existing_watch_key = ("KR", "2026-03-29", "product_safety_recall")
        db = _FakeDb(existing_event_keys={existing_key}, existing_watch_keys={existing_watch_key})
        app = self._make_app(db=db, entities=[article], tradable_map={"KR": True, "WBA": False})

        summary = app.detect_new_events(quiet=True)

        self.assertEqual(summary["skipped_duplicate_article_ticker"], 1)
        self.assertEqual(summary["watches_created"], 0)


if __name__ == "__main__":
    unittest.main()
