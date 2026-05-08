import sys
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import entity_extractor as entity_extractor_module  # noqa: E402
from entity_extractor import EntityExtractor  # noqa: E402


class EntityExtractorPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.extractor = EntityExtractor()
        # Most precision tests assert deterministic extraction behavior directly.
        self.extractor._agent_validation_enabled = False

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

    def test_product_recall_black_bean_food_nouns_are_filtered(self):
        text = "Pesticide contamination prompts black bean recall warning"
        names = self.extractor.extract_company_mentions(
            text,
            event_category="product_safety_recall",
        )
        lowered = {n.lower() for n in names}
        self.assertNotIn("black", lowered)
        self.assertNotIn("bean", lowered)
        self.assertNotIn("beans", lowered)

    def test_quote_match_requires_exact_token_for_single_word(self):
        quote = {
            "shortname": "Wheaton Precious Metals Corp",
            "longname": "Wheaton Precious Metals Corp",
            "symbol": "WPM",
            "quoteType": "EQUITY",
            "exchange": "NYQ",
        }
        self.assertFalse(self.extractor._quote_matches_company_name(quote, "Metal"))

    def test_quote_match_multiword_requires_majority_overlap(self):
        quote = {
            "shortname": "Barrick Gold Corp",
            "longname": "Barrick Gold Corp",
            "symbol": "GOLD",
            "quoteType": "EQUITY",
            "exchange": "NYQ",
        }
        self.assertFalse(self.extractor._quote_matches_company_name(quote, "TOPS Gold Pickles"))

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

    def test_gold_pickles_phrase_does_not_map_to_gold_ticker(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "strict_rules"
        extractor._agent_validation_enabled = False
        result = extractor.extract_and_map_companies(
            {
                "title": "TOPS Gold Pickles Recalled For Eruric Acid Contamination",
                "summary": "Food poisoning bulletin",
                "event_category": "product_safety_recall",
                "link": "https://example.com/tops-gold-pickles",
            },
            event_category="product_safety_recall",
        )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertNotIn("GOLD", tickers)

    def test_childrens_ibuprofen_phrase_does_not_map_to_plce(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "strict_rules"
        extractor._agent_validation_enabled = False
        result = extractor.extract_and_map_companies(
            {
                "title": "Nearly 90,000 Bottles of Children's Ibuprofen Recalled After Contamination",
                "summary": "The product, manufactured in India for Taro Pharmaceuticals, was distributed nationwide.",
                "event_category": "product_safety_recall",
                "link": "https://example.com/childrens-ibuprofen",
            },
            event_category="product_safety_recall",
        )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertNotIn("PLCE", tickers)

    def test_glass_contamination_phrase_does_not_map_to_oi(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "strict_rules"
        extractor._agent_validation_enabled = False
        result = extractor.extract_and_map_companies(
            {
                "title": "Popular grocery chain's glass contamination recall expands again",
                "summary": (
                    "Ajinomoto Foods North America Inc. recalled Trader Joe's products "
                    "after potential glass contamination."
                ),
                "event_category": "product_safety_recall",
                "link": "https://example.com/ajinomoto-glass-recall",
            },
            event_category="product_safety_recall",
        )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertNotIn("OI", tickers)

    def test_exchange_prefilter_rejects_company_ticker_mismatch(self):
        extractor = EntityExtractor()
        with patch.object(
            extractor,
            "_fetch_symbol_quote",
            return_value={
                "symbol": "PLCE",
                "quoteType": "EQUITY",
                "exchange": "NMS",
                "shortname": "The Children's Place, Inc.",
                "longname": "The Children's Place, Inc.",
            },
        ):
            verdict = extractor._prefilter_exchange_company_match("Glass", "PLCE")
        self.assertFalse(verdict.get("accepted"))

    def test_exchange_prefilter_normalizes_to_exchange_company_name(self):
        extractor = EntityExtractor()
        with patch.object(
            extractor,
            "_fetch_symbol_quote",
            return_value={
                "symbol": "WBA",
                "quoteType": "EQUITY",
                "exchange": "NMS",
                "shortname": "Walgreens Boots Alliance, Inc.",
                "longname": "Walgreens Boots Alliance, Inc.",
            },
        ):
            verdict = extractor._prefilter_exchange_company_match("Walgreens", "WBA")
        self.assertTrue(verdict.get("accepted"))
        self.assertIn("Walgreens Boots Alliance", verdict.get("normalized_company", ""))

    def test_agent_first_fail_closed_blocks_urgent_homonym(self):
        extractor = EntityExtractor()
        extractor._agent_validation_enabled = True
        extractor._agent_validation_fail_closed = True
        extractor._agent_validation_endpoint = ""
        result = extractor.extract_and_map_companies(
            {
                "title": "Urgent recall issued for beans over fears of contamination with toxic chemicals",
                "summary": "",
                "event_category": "product_safety_recall",
                "link": "https://example.com/urgent-beans",
            },
            event_category="product_safety_recall",
        )
        self.assertEqual(result.get("mapped_entities", []), [])
        self.assertTrue(result.get("rejected_entities") or result.get("mapped_candidates") == [])

    def test_agent_first_fail_closed_blocks_black_beans_homonym(self):
        extractor = EntityExtractor()
        extractor._agent_validation_enabled = True
        extractor._agent_validation_fail_closed = True
        extractor._agent_validation_endpoint = ""
        result = extractor.extract_and_map_companies(
            {
                "title": "Pesticide contamination prompts black bean recall warning",
                "summary": "",
                "event_category": "product_safety_recall",
                "link": "https://example.com/black-beans",
            },
            event_category="product_safety_recall",
        )
        self.assertEqual(result.get("mapped_entities", []), [])

    def test_agent_timeout_is_rejected_when_fail_closed(self):
        class _ReqStub:
            class RequestException(Exception):
                pass

            @staticmethod
            def post(*args, **kwargs):
                raise TimeoutError("simulated timeout")

        extractor = EntityExtractor()
        extractor._agent_validation_enabled = True
        extractor._agent_validation_fail_closed = True
        extractor._agent_validation_endpoint = "https://agent.local/validate"
        extractor._validation_mode = "agent"
        extractor._agent_validation_cache = {}
        extractor._agent_validation_cache_file = None
        original_requests = getattr(entity_extractor_module, "requests", None)
        entity_extractor_module.requests = _ReqStub
        self.addCleanup(setattr, entity_extractor_module, "requests", original_requests)
        verdict = extractor._validate_candidate_by_mode(
            article={
                "title": "Fallback Corp mentioned in ambiguous report",
                "summary": "fallback corp may be impacted",
                "link": "https://example.com/timeout-case",
            },
            candidate={"company": "Fallback Corp", "ticker": "FBK"},
            event_category="unknown_category",
            new_agent_validations_used=0,
        )
        self.assertEqual(verdict.get("validation_status"), "rejected")
        self.assertTrue(len(str(verdict.get("validation_reason", ""))) > 0)

    def test_strict_rules_mode_allows_deterministic_mapping_without_agent(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "strict_rules"
        extractor._agent_validation_enabled = False
        extractor._agent_validation_fail_closed = True
        extractor._agent_validation_endpoint = ""
        result = extractor.extract_and_map_companies(
            {
                "title": "Walgreens recalls nasal spray due to contamination",
                "summary": "",
                "event_category": "product_safety_recall",
                "link": "https://example.com/wba-recall",
            },
            event_category="product_safety_recall",
        )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertIn("WBA", tickers)

    def test_strict_rules_mode_rejects_unresolved_candidates(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "strict_rules"
        extractor._agent_validation_enabled = False
        verdict = extractor._validate_candidate_by_mode(
            article={
                "title": "Nearly 90,000 Bottles of Children's Ibuprofen Recalled",
                "summary": "manufactured in India for Taro Pharmaceuticals",
                "link": "https://example.com/childrens-ibuprofen",
            },
            candidate={"company": "Pharmaceuticals", "ticker": "ARWR"},
            event_category="product_safety_recall",
            new_agent_validations_used=0,
        )
        self.assertEqual(verdict.get("validation_status"), "rejected")
        self.assertEqual(verdict.get("validation_source"), "strict_fallback")

    def test_env_override_switches_agent_mode_to_strict_rules(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "entity_extraction": {
                            "validation_mode": "agent",
                            "agent_validation": {
                                "enabled": True,
                                "fail_closed": True,
                                "endpoint": "",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            with patch.dict("os.environ", {"CATASTROPHE_ENTITY_VALIDATION_MODE": "strict_rules"}):
                extractor = EntityExtractor(config_path=str(cfg_path))
            self.assertEqual(extractor._validation_mode, "strict_rules")
            self.assertFalse(extractor._agent_validation_enabled)

    def test_agent_is_not_called_when_strict_rules_can_decide(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "agent"
        extractor._agent_validation_enabled = True
        extractor._agent_validation_endpoint = "https://agent.local/validate"
        with patch.object(
            extractor,
            "_validate_candidate_with_agent",
            side_effect=AssertionError("agent should not be called"),
        ):
            result = extractor.extract_and_map_companies(
                {
                    "title": "Walgreens recalls nasal spray due to contamination",
                    "summary": "",
                    "event_category": "product_safety_recall",
                    "link": "https://example.com/wba-recall",
                },
                event_category="product_safety_recall",
            )
        tickers = {m["ticker"] for m in result.get("mapped_entities", [])}
        self.assertIn("WBA", tickers)

    def test_agent_cache_prevents_repeated_api_calls(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "agent"
        extractor._agent_validation_enabled = True
        extractor._agent_validation_endpoint = "https://agent.local/validate"
        extractor._agent_validation_cache = {}
        extractor._agent_validation_cache_file = None
        article = {
            "title": "Ambiguous headline mentions Fallback Corp",
            "summary": "Potentially impacted issuer discussed in mixed terms for fallback corp.",
            "link": "https://example.com/fallback-case",
        }
        candidate = {"company": "Fallback Corp", "ticker": "FBK"}
        with patch.object(
            extractor,
            "_validate_candidate_with_agent",
            return_value={
                "validation_status": "approved",
                "validation_reason": "agent approved",
                "validation_confidence": 0.8,
                "validation_engine": "agent",
            },
        ) as mock_agent:
            first = extractor._validate_candidate_by_mode(
                article=article,
                candidate=candidate,
                event_category="unknown_category",
                new_agent_validations_used=0,
            )
            second = extractor._validate_candidate_by_mode(
                article=article,
                candidate=candidate,
                event_category="unknown_category",
                new_agent_validations_used=0,
            )
        self.assertEqual(mock_agent.call_count, 1)
        self.assertEqual(first.get("validation_source"), "new")
        self.assertEqual(second.get("validation_source"), "cache")

    def test_agent_rate_limit_blocks_extra_new_validations_per_article(self):
        extractor = EntityExtractor()
        extractor._validation_mode = "agent"
        extractor._agent_validation_enabled = True
        extractor._agent_validation_max_new_per_article = 1
        verdict = extractor._validate_candidate_by_mode(
            article={"title": "Fallback Corp appears in article", "summary": "fallback corp mentioned", "link": "u"},
            candidate={"company": "Fallback Corp", "ticker": "FBK"},
            event_category="unknown_category",
            new_agent_validations_used=1,
        )
        self.assertEqual(verdict.get("validation_status"), "rejected")
        self.assertEqual(verdict.get("validation_source"), "rate_limited")

    def test_agent_payload_includes_provider_model_and_rubric_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "entity_extraction": {
                            "validation_mode": "agent",
                            "agent_validation": {
                                "enabled": True,
                                "endpoint": "https://agent.local/validate",
                                "provider": "cfg_provider",
                                "model": "cfg_model",
                                "rubric_file": "docs/ENTITY_VALIDATION_RUBRIC.md",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            captured = {}

            class _Resp:
                def raise_for_status(self):
                    return None

                @staticmethod
                def json():
                    return {"approved": True, "reason": "ok", "confidence": 0.9}

            class _ReqStub:
                @staticmethod
                def post(url, json=None, headers=None, timeout=None):
                    captured["url"] = url
                    captured["json"] = json or {}
                    return _Resp()

            original_requests = getattr(entity_extractor_module, "requests", None)
            entity_extractor_module.requests = _ReqStub
            self.addCleanup(setattr, entity_extractor_module, "requests", original_requests)

            with patch.dict(
                "os.environ",
                {
                    "CATASTROPHE_ENTITY_AGENT_PROVIDER": "env_provider",
                    "CATASTROPHE_ENTITY_AGENT_MODEL": "env_model",
                },
            ):
                extractor = EntityExtractor(config_path=str(cfg_path))
                verdict = extractor._validate_candidate_with_agent(
                    article={"title": "Some title", "summary": "Some summary", "link": "https://example.com/a"},
                    candidate={"company": "Walgreens", "ticker": "WBA"},
                    event_category="product_safety_recall",
                )
            self.assertEqual(verdict.get("validation_status"), "approved")
            self.assertEqual(captured["json"].get("provider"), "env_provider")
            self.assertEqual(captured["json"].get("model"), "env_model")
            self.assertEqual(captured["json"].get("rubric_file"), "docs/ENTITY_VALIDATION_RUBRIC.md")
            self.assertIn("Entity-to-Ticker Validation Rubric", captured["json"].get("validation_rubric_markdown", ""))

    def test_openai_compatible_provider_parses_chat_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_path = Path(tmpdir) / "settings.json"
            cfg_path.write_text(
                json.dumps(
                    {
                        "entity_extraction": {
                            "validation_mode": "agent",
                            "agent_validation": {
                                "enabled": True,
                                "endpoint": "https://api.openai.com/v1/chat/completions",
                                "provider": "openai",
                                "model": "gpt-4.1-mini",
                                "rubric_file": "docs/ENTITY_VALIDATION_RUBRIC.md",
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )

            class _Resp:
                def raise_for_status(self):
                    return None

                @staticmethod
                def json():
                    return {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "approved": True,
                                            "confidence": 0.88,
                                            "reason": "clear affected issuer",
                                            "normalized_company_name": "Walgreens Boots Alliance",
                                        }
                                    )
                                }
                            }
                        ]
                    }

            captured = {}

            class _ReqStub:
                @staticmethod
                def post(url, json=None, headers=None, timeout=None):
                    captured["url"] = url
                    captured["json"] = json or {}
                    return _Resp()

            original_requests = getattr(entity_extractor_module, "requests", None)
            entity_extractor_module.requests = _ReqStub
            self.addCleanup(setattr, entity_extractor_module, "requests", original_requests)

            extractor = EntityExtractor(config_path=str(cfg_path))
            verdict = extractor._validate_candidate_with_agent(
                article={"title": "Walgreens recalls product", "summary": "", "link": "https://example.com/r"},
                candidate={"company": "Walgreens", "ticker": "WBA"},
                event_category="product_safety_recall",
            )
            self.assertEqual(captured["json"].get("model"), "gpt-4.1-mini")
            self.assertEqual(verdict.get("validation_status"), "approved")
            self.assertEqual(verdict.get("company"), "Walgreens Boots Alliance")

    def test_strict_rules_cybersecurity_victim_pattern_approves(self):
        verdict = self.extractor._validate_candidate_with_strict_rules(
            article={
                "title": "Stryker disclosed a cybersecurity incident after a ransomware attack",
                "summary": "The company said operations were disrupted.",
            },
            candidate={"company": "Stryker", "ticker": "SYK"},
            event_category="cybersecurity",
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.get("validation_status"), "approved")

    def test_strict_rules_cybersecurity_commentary_pattern_rejects(self):
        verdict = self.extractor._validate_candidate_with_strict_rules(
            article={
                "title": "Ransomware attack hits hospital system",
                "summary": "According to security firm CrowdStrike, indicators point to known affiliates.",
            },
            candidate={"company": "CrowdStrike", "ticker": "CRWD"},
            event_category="cybersecurity",
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.get("validation_status"), "rejected")

    def test_strict_rules_clinical_sponsor_pattern_approves(self):
        verdict = self.extractor._validate_candidate_with_strict_rules(
            article={
                "title": "Sarepta announced FDA complete response letter for its Duchenne therapy",
                "summary": "",
            },
            candidate={"company": "Sarepta", "ticker": "SRPT"},
            event_category="clinical_regulatory_binary",
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.get("validation_status"), "approved")

    def test_strict_rules_clinical_comparator_pattern_rejects(self):
        verdict = self.extractor._validate_candidate_with_strict_rules(
            article={
                "title": "Biotech trial update beats expectations",
                "summary": "Analysts compared results with peer Pfizer in sector commentary.",
            },
            candidate={"company": "Pfizer", "ticker": "PFE"},
            event_category="clinical_regulatory_binary",
        )
        self.assertIsNotNone(verdict)
        self.assertEqual(verdict.get("validation_status"), "rejected")


if __name__ == "__main__":
    unittest.main()
