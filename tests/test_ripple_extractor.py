"""Tests for ripple_extractor — private company → sector proxy mapping."""
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from ripple_extractor import get_sector_proxies, enrich_with_ripple


class RippleExtractorTests(unittest.TestCase):

    def test_ransomware_title_maps_to_crwd(self):
        article = {
            "title": "Hospital hit by ransomware attack, systems offline",
            "summary": "",
            "event_category": "cybersecurity",
        }
        proxies = get_sector_proxies(article)
        tickers = [p["ticker"] for p in proxies]
        self.assertIn("CRWD", tickers)

    def test_data_breach_maps_to_cyber_stocks(self):
        article = {
            "title": "Private university suffers data breach exposing 500k records",
            "summary": "Hackers leaked student data",
            "event_category": "cybersecurity",
        }
        proxies = get_sector_proxies(article)
        self.assertTrue(len(proxies) > 0)
        for p in proxies:
            self.assertEqual(p["validation_status"], "approved")
            self.assertTrue(p["ripple"])

    def test_food_recall_maps_to_grocery(self):
        article = {
            "title": "Private food supplier issues recall over salmonella contamination",
            "summary": "",
            "event_category": "product_safety_recall",
        }
        proxies = get_sector_proxies(article)
        tickers = [p["ticker"] for p in proxies]
        self.assertTrue(any(t in tickers for t in ["SFM", "KR", "SYY"]))

    def test_unknown_category_returns_empty(self):
        article = {
            "title": "Local bakery wins award",
            "summary": "",
            "event_category": "unknown_category_xyz",
        }
        proxies = get_sector_proxies(article)
        self.assertEqual(proxies, [])

    def test_enrich_with_ripple_sets_has_publicly_traded(self):
        article = {
            "title": "Canva suffers ransomware attack",
            "summary": "",
            "event_category": "cybersecurity",
            "has_publicly_traded": False,
            "mapped_candidates": [],
        }
        enriched = enrich_with_ripple(article)
        self.assertIsNotNone(enriched)
        self.assertTrue(enriched["has_publicly_traded"])
        self.assertTrue(enriched["ripple_enriched"])
        self.assertTrue(len(enriched["mapped_candidates"]) > 0)

    def test_enrich_returns_none_for_unmapped_category(self):
        article = {
            "title": "Nothing relevant here",
            "summary": "",
            "event_category": "completely_unknown",
            "has_publicly_traded": False,
        }
        result = enrich_with_ripple(article)
        self.assertIsNone(result)

    def test_max_proxies_respected(self):
        article = {
            "title": "Hospital ransomware",
            "summary": "",
            "event_category": "cybersecurity",
        }
        proxies = get_sector_proxies(article, max_proxies=1)
        self.assertEqual(len(proxies), 1)


if __name__ == "__main__":
    unittest.main()
