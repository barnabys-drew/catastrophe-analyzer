import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from entity_extractor import EntityExtractor  # noqa: E402


class EntityExtractorPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = EntityExtractor()

    def test_product_recall_single_word_noise_is_filtered(self):
        text = (
            "Bread Sold at Trader Joe's and Other Retailers Recalled Due to "
            "Metal Contamination"
        )
        names = self.extractor.extract_company_mentions(
            text,
            event_category="product_safety_recall",
        )
        lowered = {n.lower() for n in names}
        self.assertNotIn("metal", lowered)
        self.assertNotIn("trader", lowered)
        self.assertNotIn("retailers", lowered)

    def test_product_recall_generic_lead_words_are_filtered(self):
        text = "Urgent recall issued for beans over fears of contamination with toxic chemicals"
        names = self.extractor.extract_company_mentions(
            text,
            event_category="product_safety_recall",
        )
        lowered = {n.lower() for n in names}
        self.assertNotIn("urgent", lowered)

    def test_quote_match_requires_exact_token_for_single_word(self):
        quote = {
            "shortname": "Wheaton Precious Metals Corp",
            "longname": "Wheaton Precious Metals Corp",
            "symbol": "WPM",
            "quoteType": "EQUITY",
            "exchange": "NYQ",
        }
        self.assertFalse(self.extractor._quote_matches_company_name(quote, "Metal"))

    def test_generic_single_word_lookup_is_blocked(self):
        self.assertIsNone(self.extractor.get_ticker_for_company("Metal"))
        self.assertIsNone(self.extractor.get_ticker_for_company("News"))
        self.assertIsNone(self.extractor.get_ticker_for_company("Gold"))

    def test_lowercase_leading_fragment_is_not_company_phrase(self):
        self.assertFalse(self.extractor._looks_like_company_phrase("can Stryker"))
        self.assertTrue(self.extractor._looks_like_company_phrase("Stryker Corporation"))

    def test_seeded_issuer_not_dropped_by_recall_noun_filter(self):
        text = "41K bottles of Walgreens nasal spray recalled over bacterial contamination concern"
        result = self.extractor.extract_and_map_companies(
            {"title": text, "summary": "", "event_category": "product_safety_recall"},
            event_category="product_safety_recall",
        )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertIn("WBA", tickers)


if __name__ == "__main__":
    unittest.main()
