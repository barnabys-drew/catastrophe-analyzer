"""
Entity Extractor Module
Extracts company names from breach articles and maps them to stock tickers.
Supports the full public company set via dynamic lookup (Yahoo Finance search).
"""

import re
import os
import hashlib
import math
from typing import List, Dict, Optional, Tuple
import json
from datetime import datetime, timedelta

try:
    import requests
except ImportError:
    requests = None


class EntityExtractor:
    """
    Extracts company entities from breach article text and validates ticker symbols.
    Uses a pre-seeded cache plus on-demand Yahoo Finance search for any public company.
    """

    YAHOO_SEARCH_URL = "https://query2.finance.yahoo.com/v1/finance/search"
    USER_AGENT = "Mozilla/5.0 (compatible; CatastropheAnalyzer/1.0)"
    _VALIDATION_MODES = frozenset({"agent", "strict_rules"})
    _OPENAI_COMPATIBLE_PROVIDERS = frozenset(
        {
            "openai_compatible",
            "openai",
            "openrouter",
            "groq",
            "xai",
            "together",
            "deepseek",
            "mistral",
            "fireworks",
            "ollama",
        }
    )
    _CATEGORY_SEMANTIC_RULES = {
        "cybersecurity": (
            "- Approve only if the company is the victim/operator impacted by the incident.\n"
            "- Reject security vendors, unrelated quoted experts, or generic institutions."
        ),
        "clinical_regulatory_binary": (
            "- Approve only if the company owns the drug/program tied to the trial/FDA action.\n"
            "- Reject mentions of competitors, partner comparables, or broad market commentary."
        ),
        "product_safety_recall": (
            "- Approve only if the company manufactured/distributed/retailed the recalled product.\n"
            "- Reject food nouns, adjective homonyms, and generic words (e.g. urgent, black beans)."
        ),
        "fraud_accounting_enforcement": (
            "- Approve only if the company is the subject of the accounting/enforcement action "
            "(issuer under investigation, charged, settling, or restating).\n"
            "- Reject law firms, auditors named only as advisors, unrelated quoted experts, and pure market commentary."
        ),
        "supply_chain_disruption": (
            "- Approve only if the company is directly exposed as operator, shipper, manufacturer, or named counterparty.\n"
            "- Reject generic macro commentary, unrelated ports, and logistics providers discussed only as industry backdrop."
        ),
        "financial_distress": (
            "- Approve only if the company is the issuer facing solvency, covenant, refinancing, or restructuring pressure.\n"
            "- Reject generic macro credit commentary and lenders/counsel mentioned only as counterparties."
        ),
        "dilutive_financing": (
            "- Approve only if the company is issuing equity/convertible/warrants or explicitly guiding to dilution.\n"
            "- Reject banks/underwriters mentioned solely as placement agents."
        ),
        "ma_corporate_action": (
            "- Approve only if the company is a bidder/target/issuer in the announced transaction or regulatory action.\n"
            "- Reject sector-level M&A commentary and unrelated peers."
        ),
        "leadership_scandal": (
            "- Approve only if the company is the employer/issuer tied to executive misconduct, forced departures, or board probes.\n"
            "- Reject quoted experts and firms mentioned only as comparables."
        ),
        "positive_earnings_catalyst": (
            "- Approve only if the company is the reporting issuer tied to raised guidance, beat, or positive preannouncement.\n"
            "- Reject broad market recap mentions without issuer-specific results context."
        ),
    }

    # Yahoo / search "exchange" values that indicate US listing (major venues).
    _US_EXCHANGES = frozenset({
        "NMS", "NAS", "NGM", "NCM", "NYQ", "NYM", "PCX", "ASE", "BTS", "CBOE",
        "NASDAQ", "NYSE", "NYSEARCA", "AMEX", "NYSE MKT", "OTC", "PNK", "BATS",
    })

    # Never treat as a company for ticker lookup (countries, generic headline words).
    _ENTITY_BLOCKLIST = frozenset({
        "iran", "iraq", "china", "russia", "india", "israel", "ukraine", "brazil",
        "korea", "japan", "france", "germany", "canada", "mexico", "europe", "nato",
        "things", "internet", "department", "huge", "manager", "services", "actions",
        "geopolitical", "identity", "emergency", "medtech", "magento", "federal", "feds",
        "botnets", "android", "signal", "github", "azure",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "winter", "summer", "spring", "fall", "government", "security", "national",
        "american", "european", "asian", "global", "public", "private", "critical",
        "firm", "maker", "device", "medical", "attack", "attacks", "phishing",
    })

    _BLOCKLIST_PHRASES = frozenset({
        "medtech firm", "medical device", "device maker", "identity manager",
        "git hub", "e stores",
    })

    # Generic single-word nouns frequently found in recall/cyber headlines.
    # These should not be treated as standalone public company entities.
    _GENERIC_SINGLE_WORD_ENTITIES = frozenset({
        "affairs", "alert", "back", "black", "bean", "beans", "berry", "berries",
        "bread", "children", "contamination", "cyber",
        "event", "food", "foods", "health", "help", "here", "homeland", "impact",
        "injury", "item", "items", "life", "market", "material", "medical", "metal",
        "glass", "shard", "shards", "fragments", "foreign", "substance",
        "news", "organic", "other", "pharma", "poisoning", "product", "prompts",
        "recall", "recalled", "bulletin", "eruric", "urgent", "urgently", "yahoo", "msn",
        "retailer", "retailers", "rice", "risk", "safety", "sold", "technical",
        "trader", "trio", "warning",
        # Hardware/memory technology acronyms — Yahoo Finance resolves these to ETF tickers
        # (e.g. DRAM ETF) but they appear in recall/cyber headlines as generic tech terms.
        "dram", "sram", "nand", "nvme", "flash",
        # Common generic words that Yahoo Finance search returns tickers for but are never
        # standalone company identifiers in catastrophe-event headlines.
        "assets", "automotive", "brands", "business", "caring", "cloud", "connect",
        "county", "credit", "data", "design", "digital", "distribution", "driven",
        "eastern", "enable", "equity", "finance", "growth", "industrial", "infrastructure",
        "innovation", "insurance", "island", "journal", "league", "logistics",
        "manufacturing", "metals", "mining", "motion", "networks", "northern",
        "operations", "pacific", "payments", "personal", "platform", "records",
        "remote", "sharing", "social", "solutions", "southern", "sports", "strategy",
        "supply", "systems", "transportation", "travel", "ventures", "vision",
        "western", "county", "states", "senior", "social", "second",
    })
    _LOWERCASE_GLUE_WORDS = frozenset({"and", "of", "the", "for", "at", "&"})
    _RECALL_SINGLE_WORD_ALLOWLIST = frozenset(
        {
            "walgreens",
            "kroger",
            "costco",
            "target",
            "walmart",
            "amazon",
            "cvs",
        }
    )

    # Minimum length for fuzzy substring match against seed map (avoids "ge" in "geopolitical" -> GE).
    _MIN_PARTIAL_NAME_LEN = 5
    _TRAILING_TRIM_WORDS = frozenset({
        "for", "in", "on", "after", "amid", "as", "with", "from", "into", "at",
    })

    def __init__(self, config_path: Optional[str] = None):
        """Initialize with common company patterns and optional config."""
        if config_path is None:
            # Default: config next to repo root when running from src/
            _dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(_dir, "..", "config", "settings.json")
        self.company_patterns = [
            r'(?:Inc|Inc\.|Corp|Corp\.|Company|Co\.|Ltd|LLC|CORPORATION|CORPORATION\.)',
            r'(?:\(.*?\))',  # Parenthetical company identifiers
        ]

        # Common cybersecurity-related entity keywords
        self.entity_keywords = [
            'hospital', 'bank', 'university', 'school', 'government',
            'airline', 'retail', 'manufacturing', 'healthcare',
            'telecom', 'technology', 'software', 'financial',
            'energy', 'oil', 'gas', 'insurance', 'services'
        ]

        # Config: dynamic lookup and cache (defaults)
        self._config = self._load_config(config_path)
        self._us_listed_only = self._config.get("us_listed_equities_only", True)
        self._use_dynamic_lookup = self._config.get("use_dynamic_lookup", True)
        self._cache_lookups = self._config.get("cache_lookups", True)
        self._cache_file = self._config.get("cache_file")  # optional path
        self._require_exchange_company_verification = bool(
            self._config.get("require_exchange_company_verification", True)
        )
        self._exchange_verification_fail_closed = bool(
            self._config.get("exchange_verification_fail_closed", True)
        )
        self._agent_validation = self._config.get("agent_validation", {}) or {}
        self._validation_mode = self._resolve_validation_mode(self._config, self._agent_validation)
        self._agent_validation_enabled = self._validation_mode == "agent"
        self._agent_validation_fail_closed = bool(self._agent_validation.get("fail_closed", True))
        self._agent_validation_timeout_seconds = int(self._agent_validation.get("timeout_seconds", 8))
        self._agent_validation_endpoint = str(
            os.getenv("CATASTROPHE_ENTITY_AGENT_ENDPOINT")
            or self._agent_validation.get("endpoint", "")
            or ""
        ).strip()
        self._agent_validation_api_key = str(
            os.getenv("CATASTROPHE_ENTITY_AGENT_API_KEY")
            or self._agent_validation.get("api_key", "")
            or ""
        ).strip()
        self._agent_validation_provider = str(
            os.getenv("CATASTROPHE_ENTITY_AGENT_PROVIDER")
            or self._agent_validation.get("provider", "")
            or "generic_http"
        ).strip()
        self._agent_validation_model = str(
            os.getenv("CATASTROPHE_ENTITY_AGENT_MODEL")
            or self._agent_validation.get("model", "")
            or ""
        ).strip()
        self._agent_validation_max_candidates = max(
            1, int(self._agent_validation.get("max_candidates_per_article", 5))
        )
        self._agent_validation_max_new_per_article = max(
            0, int(self._agent_validation.get("max_new_validations_per_article", 1))
        )
        self._agent_validation_cache_file = self._agent_validation.get("cache_file")
        self._agent_validation_cache_ttl_days = max(
            1, int(self._agent_validation.get("cache_ttl_days", 60))
        )
        self._agent_validation_cache: Dict[str, Dict] = {}
        self._validation_rubric_path = str(
            os.getenv("CATASTROPHE_ENTITY_VALIDATION_RUBRIC_FILE")
            or self._agent_validation.get("rubric_file", "")
            or "docs/ENTITY_VALIDATION_RUBRIC.md"
        ).strip()
        self._validation_rubric_markdown = self._load_validation_rubric(self._validation_rubric_path)

        # Pre-seeded cache (fast path); also stores results from dynamic lookups
        self.company_to_ticker = {
            # Large tech companies
            'apple': 'AAPL',
            'microsoft': 'MSFT',
            'google': 'GOOGL',
            'alphabet': 'GOOGL',
            'amazon': 'AMZN',
            'meta': 'META',
            'facebook': 'META',
            'twitter': 'TWTR',
            'x corporation': 'TWTR',
            'nvidia': 'NVDA',
            'amd': 'AMD',
            'intel': 'INTC',
            'cisco': 'CSCO',
            'ibm': 'IBM',
            'oracle': 'ORCL',
            'salesforce': 'CRM',
            'adobe': 'ADBE',
            'zoom': 'ZM',
            'slack': 'SLACK',
            'crowdstrike': 'CRWD',
            'palo alto': 'PANW',
            'fortinet': 'FTNT',
            'cloudflare': 'NET',

            # Financial and Services
            'jpmorgan': 'JPM',
            'j.p. morgan': 'JPM',
            'bank of america': 'BAC',
            'citigroup': 'C',
            'wells fargo': 'WFC',
            'goldman sachs': 'GS',
            'morgan stanley': 'MS',
            'capital one': 'COF',
            'american express': 'AXP',
            'visa': 'V',
            'mastercard': 'MA',
            'paypal': 'PYPL',
            'square': 'SQ',
            'stripe': 'UNKNOWN',
            'coinbase': 'COIN',

            # Healthcare and Pharma
            'johnson & johnson': 'JNJ',
            'pfizer': 'PFE',
            'moderna': 'MRNA',
            'merck': 'MRK',
            'eli lilly': 'LLY',
            'astrazeneca': 'AZN',
            'unitedhealth': 'UNH',
            'cvs health': 'CVS',
            'walgreens': 'WBA',
            'anthem': 'ANTM',

            # Retail and Consumer
            'walmart': 'WMT',
            'target': 'TGT',
            'costco': 'COST',
            'amazon': 'AMZN',
            'ebay': 'EBAY',
            'home depot': 'HD',
            'lowes': 'LOW',
            'best buy': 'BBY',
            'nike': 'NKE',
            'adidas': 'ADDYY',

            # Telecommunications
            'at&t': 'T',
            'verizon': 'VZ',
            'comcast': 'CMCSA',
            't-mobile': 'TMUS',
            'charter': 'CHTR',

            # Airlines and Transportation
            'delta': 'DAL',
            'united': 'UAL',
            'american': 'AAL',
            'southwest': 'LUV',

            # Energy
            'exxon': 'XOM',
            'chevron': 'CVX',
            'shell': 'SHEL',
            'bp': 'BP',

            # Industrial/Manufacturing
            'boeing': 'BA',
            'lockheed martin': 'LMT',
            'ge': 'GE',
            'general electric': 'GE',
            'stryker': 'SYK',
            'stryker corporation': 'SYK',
        }

        # In-memory lookup cache (dynamic lookups added here when cache_lookups is True)
        self._lookup_cache: Dict[str, Optional[str]] = {}
        self._symbol_quote_cache: Dict[str, Optional[Dict]] = {}
        self._company_ticker_verify_cache: Dict[str, Dict] = {}
        if self._cache_file and os.path.isfile(self._cache_file):
            self._load_lookup_cache()
        if self._agent_validation_cache_file and os.path.isfile(self._agent_validation_cache_file):
            self._load_agent_validation_cache()

        self.ticker_to_company = {v: k for k, v in self.company_to_ticker.items()}

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load entity_extraction section from config file."""
        defaults = {
            "use_dynamic_lookup": True,
            "cache_lookups": True,
            "cache_file": None,
            "us_listed_equities_only": True,
            "require_exchange_company_verification": True,
            "exchange_verification_fail_closed": True,
            "validation_mode": "strict_rules",
            "agent_validation": {
                "enabled": False,
                "fail_closed": True,
                "timeout_seconds": 8,
                "endpoint": "",
                "api_key": "",
                "provider": "generic_http",
                "model": "",
                "max_candidates_per_article": 5,
                "max_new_validations_per_article": 1,
                "cache_file": "../data/entity_validation_cache.json",
                "cache_ttl_days": 60,
                "rubric_file": "docs/ENTITY_VALIDATION_RUBRIC.md",
            },
        }
        if not config_path:
            return defaults
        try:
            with open(config_path, "r") as f:
                full = json.load(f)
            section = full.get("entity_extraction", {})
            return {**defaults, **section}
        except (FileNotFoundError, json.JSONDecodeError):
            return defaults

    def _resolve_validation_mode(self, config: Dict, agent_cfg: Dict) -> str:
        """
        Determine validation mode from config and optional env override.

        Modes:
        - strict_rules: deterministic filtering only
        - agent: agent-first semantic approval
        """
        mode = str(config.get("validation_mode", "") or "").strip().lower()
        if mode not in self._VALIDATION_MODES:
            mode = "agent" if bool(agent_cfg.get("enabled", False)) else "strict_rules"
        env_mode = str(os.getenv("CATASTROPHE_ENTITY_VALIDATION_MODE", "") or "").strip().lower()
        if env_mode in self._VALIDATION_MODES:
            mode = env_mode
        return mode

    def _load_validation_rubric(self, rubric_path: str) -> str:
        """Load markdown rubric used by agent validation prompt."""
        rp = (rubric_path or "").strip()
        try:
            if not rp:
                raise OSError("missing rubric path")
            if os.path.isabs(rp):
                candidate = rp
            else:
                here = os.path.dirname(os.path.abspath(__file__))
                candidate = os.path.normpath(os.path.join(here, "..", rp))
            with open(candidate, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return (
                "## Entity Validation Rubric\n"
                "- Approve only if the article clearly identifies the public company as affected.\n"
                "- Reject homonyms, generic nouns, and unrelated company mentions.\n"
            )

    def _load_lookup_cache(self) -> None:
        """Load persisted lookup cache from cache_file into cache and company_to_ticker."""
        if not self._cache_file:
            return
        try:
            with open(self._cache_file, "r") as f:
                data = json.load(f)
            skipped = 0
            for k, v in data.items():
                if v and v != "UNKNOWN":
                    if self._us_listed_only and not self._is_us_primary_symbol(str(v)):
                        continue
                    key = k.lower()
                    # Reject single-word generic entries that poison entity extraction.
                    parts = self._tokenize_name(key)
                    if len(parts) == 1:
                        w = parts[0]
                        if w in self._GENERIC_SINGLE_WORD_ENTITIES or w in self._ENTITY_BLOCKLIST:
                            skipped += 1
                            continue
                    self._lookup_cache[key] = v
                    self.company_to_ticker[key] = v
            if skipped:
                print(f"[entity_extractor] Skipped {skipped} generic single-word cache entries on load.", flush=True)
            self.ticker_to_company = {v: k for k, v in self.company_to_ticker.items()}
        except (FileNotFoundError, json.JSONDecodeError):
            pass

    def _save_lookup_cache(self) -> None:
        """Persist lookup cache to cache_file (only dynamic entries beyond initial seed)."""
        if not self._cache_file:
            return
        try:
            with open(self._cache_file, "w") as f:
                json.dump(self._lookup_cache, f, indent=2)
        except OSError:
            pass

    def _load_agent_validation_cache(self) -> None:
        """Load persisted agent validation cache keyed by article+candidate fingerprint."""
        if not self._agent_validation_cache_file:
            return
        try:
            with open(self._agent_validation_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._agent_validation_cache = data
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            self._agent_validation_cache = {}

    def _save_agent_validation_cache(self) -> None:
        if not self._agent_validation_cache_file:
            return
        try:
            with open(self._agent_validation_cache_file, "w", encoding="utf-8") as f:
                json.dump(self._agent_validation_cache, f, indent=2)
        except OSError:
            pass

    @staticmethod
    def _norm_text(value: str) -> str:
        return " ".join(str(value or "").strip().lower().split())

    def _validation_cache_key(self, article: Dict, candidate: Dict, event_category: str) -> str:
        raw = "|".join(
            [
                self._norm_text(event_category),
                self._norm_text(article.get("link", article.get("url", ""))),
                self._norm_text(article.get("title", "")),
                self._norm_text(candidate.get("company", "")),
                self._norm_text(candidate.get("ticker", "")),
            ]
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _get_cached_agent_validation(self, cache_key: str) -> Optional[Dict]:
        row = self._agent_validation_cache.get(cache_key)
        if not isinstance(row, dict):
            return None
        cached_at = str(row.get("cached_at", "") or "").strip()
        if not cached_at:
            return row.get("verdict")
        try:
            dt = datetime.fromisoformat(cached_at)
        except ValueError:
            return row.get("verdict")
        if dt + timedelta(days=self._agent_validation_cache_ttl_days) < datetime.now():
            return None
        return row.get("verdict")

    @staticmethod
    def _is_us_primary_symbol(symbol: str) -> bool:
        """Reject foreign listings (e.g. RANI3.SA); allow optional class suffix BRK.A."""
        if not symbol:
            return False
        s = symbol.upper().strip()
        if re.search(
            r"\.(SA|L|DE|F|VI|HK|KS|T|AX|TO|PA|MI|AS|SW|ST|BR|MX|NS|BO)$",
            s,
        ):
            return False
        if "." in s:
            return bool(re.match(r"^[A-Z]{1,5}\.[A-Z]$", s))
        return bool(re.match(r"^[A-Z]{1,5}$", s))

    def _yahoo_quote_is_us_equity(self, quote: Dict) -> bool:
        if (quote.get("quoteType") or "").upper() != "EQUITY":
            return False
        sym = (quote.get("symbol") or "").strip().upper()
        if not self._is_us_primary_symbol(sym):
            return False
        if not self._us_listed_only:
            return True
        ex = (quote.get("exchange") or "").strip().upper()
        if not ex:
            return True
        if ex in self._US_EXCHANGES:
            return True
        if "NASDAQ" in ex or "NYSE" in ex or "AMEX" in ex or "BATS" in ex:
            return True
        return False

    def _dynamic_lookup_company(self, company_name: str) -> Optional[str]:
        """
        Resolve company name to ticker via Yahoo Finance search API.
        When us_listed_equities_only: first match that is US-listed equity only.
        """
        if not requests:
            return None
        name = (company_name or "").strip()
        if not name or len(name) < 2:
            return None
        try:
            resp = requests.get(
                self.YAHOO_SEARCH_URL,
                params={"q": name, "quotes_count": 12},
                headers={"User-Agent": self.USER_AGENT},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
        except (requests.RequestException, ValueError, KeyError):
            return None
        quotes = data.get("quotes", [])
        for q in quotes:
            if not self._yahoo_quote_is_us_equity(q):
                continue
            if not self._quote_matches_company_name(q, name):
                continue
            sym = (q.get("symbol") or "").strip()
            if sym:
                return sym.upper()
        return None

    def _fetch_symbol_quote(self, ticker: str) -> Optional[Dict]:
        sym = (ticker or "").strip().upper()
        if not sym:
            return None
        if sym in self._symbol_quote_cache:
            return self._symbol_quote_cache[sym]
        if not requests:
            self._symbol_quote_cache[sym] = None
            return None
        try:
            resp = requests.get(
                self.YAHOO_SEARCH_URL,
                params={"q": sym, "quotes_count": 10},
                headers={"User-Agent": self.USER_AGENT},
                timeout=8,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            self._symbol_quote_cache[sym] = None
            return None
        quote = None
        for q in data.get("quotes", []) or []:
            if (q.get("symbol") or "").strip().upper() != sym:
                continue
            if not self._yahoo_quote_is_us_equity(q):
                continue
            quote = q
            break
        self._symbol_quote_cache[sym] = quote
        return quote

    def _prefilter_exchange_company_match(self, company: str, ticker: str) -> Dict:
        """
        Verify the extracted company+ticker pair resolves to a valid US-listed equity issuer.
        Returns accepted flag, optional normalized company name, and reject reason.
        """
        if not self._require_exchange_company_verification:
            return {"accepted": True, "normalized_company": company}

        company_norm = (company or "").strip()
        ticker_norm = (ticker or "").strip().upper()
        cache_key = f"{company_norm.lower()}|{ticker_norm}"
        cached = self._company_ticker_verify_cache.get(cache_key)
        if cached:
            return cached

        quote = self._fetch_symbol_quote(ticker_norm)
        if quote:
            if self._quote_matches_company_name(quote, company_norm):
                canonical = (
                    (quote.get("longname") or quote.get("shortname") or company_norm).strip()
                )
                out = {"accepted": True, "normalized_company": canonical}
                self._company_ticker_verify_cache[cache_key] = out
                return out
            out = {
                "accepted": False,
                "reason": "company name does not match exchange-listed issuer metadata",
            }
            self._company_ticker_verify_cache[cache_key] = out
            return out

        # Seed map fallback when quote metadata is temporarily unavailable.
        seeded_name = (self.ticker_to_company.get(ticker_norm) or "").strip()
        if seeded_name and self._quote_matches_company_name(
            {"shortname": seeded_name, "longname": seeded_name}, company_norm
        ):
            out = {"accepted": True, "normalized_company": seeded_name.title()}
            self._company_ticker_verify_cache[cache_key] = out
            return out

        # If quote verification is unavailable, fail according to policy.
        if self._exchange_verification_fail_closed:
            out = {
                "accepted": False,
                "reason": "unable to verify exchange-listed issuer metadata",
            }
            self._company_ticker_verify_cache[cache_key] = out
            return out
        out = {"accepted": True, "normalized_company": company_norm}
        self._company_ticker_verify_cache[cache_key] = out
        return out

    @staticmethod
    def _tokenize_name(value: str) -> List[str]:
        if not value:
            return []
        return [t for t in re.split(r"[^a-z0-9]+", value.lower()) if t]

    def _is_generic_company_name(self, company_name: str) -> bool:
        key = (company_name or "").strip().lower()
        if not key:
            return True
        if key in self._ENTITY_BLOCKLIST or key in self._BLOCKLIST_PHRASES:
            return True
        parts = self._tokenize_name(key)
        if len(parts) == 1 and parts[0] in self._GENERIC_SINGLE_WORD_ENTITIES:
            return True
        return False

    def _looks_like_company_phrase(self, company_name: str) -> bool:
        """
        Guardrail against phrases like "can Stryker" extracted from sentence fragments.
        """
        raw_tokens = [t for t in re.split(r"\s+", (company_name or "").strip()) if t]
        if not raw_tokens:
            return False
        for tok in raw_tokens:
            clean = re.sub(r"[^A-Za-z0-9&.\-']", "", tok)
            if not clean:
                continue
            lower = clean.lower()
            if lower in self._LOWERCASE_GLUE_WORDS:
                continue
            if clean.isupper():
                continue
            if clean[0].isupper():
                continue
            return False
        return True

    def _quote_matches_company_name(self, quote: Dict, company_name: str) -> bool:
        """
        Require name-level relevance for dynamic lookup.

        This avoids generic noun mappings such as "Metal" -> metals/mining equities.
        """
        query_tokens = self._tokenize_name(company_name)
        if not query_tokens:
            return False

        quote_name = " ".join(
            [
                str(quote.get("shortname") or ""),
                str(quote.get("longname") or ""),
            ]
        ).strip().lower()
        quote_tokens = set(self._tokenize_name(quote_name))
        if not quote_tokens:
            return False

        # For single-word queries, require exact token match (not stemming/plural-only).
        if len(query_tokens) == 1:
            token = query_tokens[0]
            if token in self._GENERIC_SINGLE_WORD_ENTITIES:
                return False
            return token in quote_tokens

        overlap = sum(1 for t in query_tokens if t in quote_tokens)
        needed = max(1, int(math.ceil(len(query_tokens) * 0.6)))
        return overlap >= needed

    def extract_company_mentions(self, text: str, event_category: Optional[str] = None) -> List[str]:
        """
        Extract potential company names from text.
        Includes standalone names (e.g. "Stryker was hacked") and Inc/Corp patterns.
        """
        companies = []

        # Patterns like "Company Name Inc." or "Company Name Corp." (limit to 3 words to avoid sentence capture)
        # Limit to 1-2 word company names to avoid capturing generic phrases
        # (e.g. "Medtech Firm Stryker" -> should ideally yield "Stryker").
        patterns = [
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:Inc|Corp|Ltd|LLC)\.?",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:announced|said|reported|confirmed|disclosed)\s+",
            # Standalone company name before breach-related verbs: "Stryker was hacked"
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:was|is|has been|gets|got)\s+(?:hacked|breached|compromised|attacked|hit)",
            r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})\s+(?:says|confirmed|reported|announced|disclosed)\s+",
            # After breach context: "breach at Stryker", "attack on Microsoft"
            r"(?:breach|attack|incident|ransomware|hack)\s+(?:at|on|hits?)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,1})",
        ]
        if event_category == "cybersecurity":
            patterns.extend(
                [
                    # "Company discloses SEC/8-K cybersecurity incident ..."
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:discloses?|disclosed|files?|filed|reports?|reported)\s+"
                    r"(?:a\s+)?(?:material\s+)?(?:cybersecurity incident|security incident|8-k|sec filing)",
                    # "Ransomware attack hits Company"
                    r"(?:ransomware|cyberattack|hack(?:ed|ers?)?|security incident)\s+"
                    r"(?:hits?|targets?|at|on)\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                ]
            )
        elif event_category == "clinical_regulatory_binary":
            patterns.extend(
                [
                    # "Company announced phase 3/topline/FDA decision ..."
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:announced|reports?|reported|posted|disclosed)\s+"
                    r"(?:phase\s*(?:2|ii|3|iii)|topline|top-line|fda|clinical|trial)",
                    # "FDA issues CRL to Company"
                    r"(?:fda|food and drug administration)\s+(?:issues?|issued|sent)\s+"
                    r"(?:a\s+)?(?:complete response letter|crl)\s+to\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                    # "Company receives FDA approval"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:receives?|received|wins?|won|gets?|got)\s+"
                    r"(?:fda approval|approval|complete response letter|crl|clinical hold)",
                ]
            )
        elif event_category == "product_safety_recall":
            patterns.extend(
                [
                    # "Company recalls ...", "Company issues safety alert ..."
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:recalls?|recalled|issues?|issued|announces?|announced)\s+"
                    r"(?:a\s+)?(?:product recall|safety recall|recall|safety alert|warning letter)",
                    # "CPSC/FDA warning letter to Company"
                    r"(?:cpsc|consumer product safety commission|fda|food and drug administration)\s+"
                    r"(?:issues?|issued|sent)\s+"
                    r"(?:a\s+)?(?:warning letter|recall notice|safety alert)\s+to\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                    # "Company grounds/halts production ..."
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:grounds?|grounded|halts?|halted|suspends?|suspended)\s+"
                    r"(?:production|shipments?|operations|product line)",
                ]
            )
        elif event_category == "fraud_accounting_enforcement":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:announces?|discloses?|reports?|reported)\s+"
                    r"(?:a\s+)?(?:restatement|accounting review|internal investigation)",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:restates?|revised)\s+(?:financial|results|earnings)",
                    r"(?:sec|securities and exchange commission)\s+"
                    r"(?:charges|alleges|announces charges against|files complaint against)\s+"
                    r"(?:[A-Za-z]+\s+)?([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                    r"(?:sec|securities and exchange commission)\s+"
                    r"(?:settles|settled)\s+with\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                ]
            )
        elif event_category == "supply_chain_disruption":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:says|said|reports?|reported|announces?|announced)\s+"
                    r"(?:a\s+)?(?:supply chain|production|shipping|logistics|factory|plant)\s+",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:halts?|halted|suspends?|suspended|shuts?|shut down)\s+"
                    r"(?:production|operations|plant|factory|assembly)",
                    r"(?:disruption|shortage|delay)\s+(?:at|for)\s+"
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                ]
            )
        elif event_category == "financial_distress":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:files?|filed|seeks?|sought|announces?|announced)\s+"
                    r"(?:a\s+)?(?:chapter\s*11|bankruptcy|restructuring|forbearance|debt exchange)",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:warns?|warned|discloses?|disclosed|reports?|reported)\s+"
                    r"(?:a\s+)?(?:going concern|liquidity crisis|covenant breach|payment default)",
                ]
            )
        elif event_category == "dilutive_financing":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:announces?|announced|prices?|priced|launches?|launched)\s+"
                    r"(?:a\s+)?(?:secondary offering|follow-on offering|at-the-market|atm offering|registered direct offering|private placement)",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:issues?|issued|sells?|sold)\s+"
                    r"(?:convertible notes|convertible preferred|warrants|shares)",
                ]
            )
        elif event_category == "ma_corporate_action":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:acquires?|acquired|to acquire|to be acquired by|merges?|merged)\s+",
                    r"(?:tender offer|hostile bid|competing bid|merger agreement)\s+"
                    r"(?:for|by|from)\s+([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})",
                ]
            )
        elif event_category == "leadership_scandal":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:ceo|cfo|chairman|chief executive|chief financial officer)\s+"
                    r"(?:resigns?|resigned|steps down|stepped down|is fired|was fired|terminated)",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:faces?|facing|announces?|announced|discloses?|disclosed)\s+"
                    r"(?:a\s+)?(?:board investigation|ethics probe|whistleblower complaint|executive misconduct)",
                ]
            )
        elif event_category == "positive_earnings_catalyst":
            patterns.extend(
                [
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:raises?|raised|increases?|increased|reaffirms?|reaffirmed)\s+"
                    r"(?:guidance|outlook|forecast)",
                    r"([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,2})\s+"
                    r"(?:beats?|beat|reports?|reported|posts?|posted)\s+"
                    r"(?:estimates|expectations|record revenue|eps beat|revenue beat)",
                ]
            )

        for pattern in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                # Handle different group positions (some patterns capture company in group 1)
                company_name = (match.group(1) or "").strip()
                if len(company_name) > 2 and company_name not in ("The", "The Company", "A"):
                    companies.append(company_name)

        # Single capitalized word (4+ chars) in breach context: "Stryker hacked" or "breach at Stryker"
        min_len = self._config.get("min_company_name_length", 2)
        breach_words = (
            "breach hacked hack hackers hacktivist cyberattack ransomware exploit vulnerability "
            "compromised attacked attack incident disclosed announced wiper wipe wiped data-wiping data wipe"
        )
        clinical_words = (
            "fda approval complete response letter crl clinical hold trial hold phase 2 phase 3 "
            "phase ii phase iii topline top-line endpoint adverse event safety signal pdufa nda bla"
        )
        cyber_words = (
            "material cybersecurity incident unauthorized access exfiltration sec filing 8-k zero-day "
            "destructive malware wiper service outage operations disrupted supply chain attack data leak"
        )
        product_safety_words = (
            "recall product recall safety recall grounding safety alert warning letter defect defective "
            "contamination injury injuries production halt stop sale do not use cpsc nhtsa faa"
        )
        fraud_enforcement_words = (
            "restatement securities fraud accounting fraud sec charges indictment enforcement "
            "wells notice material weakness internal control subpoena guilty plea civil complaint "
            "department of justice accounting irregularities misstated financial revenue recognition "
            "disgorgement cease and desist administrative proceeding fcpa insider trading wire fraud "
            "market manipulation delisting trading halt finra deferred prosecution pcaob audit committee "
            "earnings restatement accounting probe"
        )
        supply_chain_words = (
            "supply chain disruption logistics shipping delay port congestion factory fire plant shutdown "
            "production halt semiconductor shortage chip shortage inventory shortage supplier bankruptcy "
            "force majeure freight backlog container shortage strike logistics disruption manufacturing"
        )
        financial_distress_words = (
            "chapter 11 chapter 7 bankruptcy restructuring going concern covenant breach covenant default "
            "payment default missed interest forbearance liquidity crisis insolvency debt exchange debt maturity"
        )
        dilutive_financing_words = (
            "secondary offering follow-on offering at-the-market atm offering registered direct offering "
            "private placement convertible notes convertible preferred warrant issuance dilution equity raise "
            "shelf registration rights offering pipe financing priced at discount"
        )
        ma_words = (
            "acquisition merger agreement take-private buyout tender offer hostile bid competing bid "
            "deal termination deal break antitrust challenge doj sues to block ftc sues to block divestiture"
        )
        leadership_scandal_words = (
            "ceo resigns cfo resigns forced resignation terminated for cause executive misconduct "
            "board investigation ethics probe whistleblower complaint compliance failure governance failure"
        )
        positive_earnings_words = (
            "raised guidance guidance increased beat estimates beats on revenue record revenue margin expansion "
            "above consensus positive preannouncement strong quarter improved outlook"
        )
        context_words = breach_words
        if event_category == "cybersecurity":
            context_words = f"{breach_words} {cyber_words}"
        elif event_category == "clinical_regulatory_binary":
            context_words = f"{breach_words} {clinical_words}"
        elif event_category == "product_safety_recall":
            context_words = f"{breach_words} {product_safety_words}"
        elif event_category == "fraud_accounting_enforcement":
            context_words = f"{breach_words} {fraud_enforcement_words}"
        elif event_category == "supply_chain_disruption":
            context_words = f"{breach_words} {supply_chain_words}"
        elif event_category == "financial_distress":
            context_words = f"{breach_words} {financial_distress_words}"
        elif event_category == "dilutive_financing":
            context_words = f"{breach_words} {dilutive_financing_words}"
        elif event_category == "ma_corporate_action":
            context_words = f"{breach_words} {ma_words}"
        elif event_category == "leadership_scandal":
            context_words = f"{breach_words} {leadership_scandal_words}"
        elif event_category == "positive_earnings_catalyst":
            context_words = f"{breach_words} {positive_earnings_words}"
        stop_words = (
            "the and said have this that with from when company medical device maker firm "
            "medical medtech device maker monday tuesday wednesday thursday friday saturday "
            "sunday security week breach city state country region european internet union claim "
            "center management iran iraq china russia india israel brazil canada japan france "
            "germany korea ukraine nato federal feds department identity emergency geopolitical "
            "magento actions manager services things internet huge botnets phishing android "
            "signal github azure monitor magento identity things department fda phase trial topline"
        ).split()
        text_lower = text.lower()
        for m in re.finditer(r"\b([A-Z][a-z]{3,})\b", text):
            name = m.group(1)
            if name.lower() in stop_words:
                continue
            if name.lower() in self._GENERIC_SINGLE_WORD_ENTITIES:
                continue
            if event_category == "product_safety_recall":
                # Food/safety headlines often capitalize nouns that are not issuers.
                noun_after = (
                    r"(?:recall|recalled|warning|contamination|bean|beans|bread|rice|pickles?|"
                    r"chicken|vegetable|nasal|bottles?|toys?|products?|ibuprofen|acetaminophen|"
                    r"syrup|capsules?|tablets?|issued|sold|due)"
                )
                # Keep known seeded issuers (e.g. Walgreens) even when followed by product nouns.
                if (
                    name.lower() not in self._RECALL_SINGLE_WORD_ALLOWLIST
                    and (
                        re.search(rf"\b{re.escape(name.lower())}\s+{noun_after}\b", text_lower)
                        or re.search(rf"\b{re.escape(name.lower())}'s\s+{noun_after}\b", text_lower)
                    )
                ):
                    continue
            # Must appear near a breach-related word (same sentence or within ~40 chars)
            start = max(0, m.start() - 50)
            end = min(len(text), m.end() + 50)
            snippet = text_lower[start:end]
            if any(bw in snippet for bw in context_words.split()):
                companies.append(name)

        return self._clean_company_mentions(companies)

    def _clean_company_mentions(self, raw_companies: List[str]) -> List[str]:
        """Normalize and dedupe extracted company mentions."""
        cleaned: List[str] = []
        for raw in raw_companies:
            name = re.sub(r"\s+", " ", (raw or "").strip(" ,.;:-")).strip()
            if not name:
                continue
            parts = name.split()
            while parts and parts[-1].lower() in self._TRAILING_TRIM_WORDS:
                parts = parts[:-1]
            if not parts:
                continue
            name = " ".join(parts)
            if len(name) < 3:
                continue
            if self._is_generic_company_name(name):
                continue
            cleaned.append(name)

        # Keep longer/more-specific names first (e.g. "Sarepta Therapeutics" over "Sarepta").
        unique = sorted(set(cleaned), key=lambda x: (-len(x), x))
        kept: List[str] = []
        for candidate in unique:
            padded = f" {candidate.lower()} "
            if any(padded in f" {k.lower()} " for k in kept):
                continue
            kept.append(candidate)
        return kept

    def get_ticker_for_company(self, company_name: str) -> Optional[str]:
        """
        Get stock ticker for a company name.
        Uses cache/static map first, then dynamic Yahoo Finance search for full public set.
        """
        normalized_name = company_name.lower().strip()
        if not normalized_name:
            return None
        if self._is_generic_company_name(normalized_name):
            return None
        if not self._looks_like_company_phrase(company_name):
            return None

        # Fast path: direct match
        if normalized_name in self.company_to_ticker:
            ticker = self.company_to_ticker[normalized_name]
            if ticker == "UNKNOWN":
                return None
            if self._us_listed_only and not self._is_us_primary_symbol(ticker):
                return None
            return ticker

        # Partial match (longer seed keys, word-boundary style — avoids "united" in "unitedhealth")
        padded = f" {normalized_name} "
        for known_name, ticker in self.company_to_ticker.items():
            if len(known_name) < self._MIN_PARTIAL_NAME_LEN:
                continue
            in_padded = f" {known_name} " in padded
            at_start = normalized_name.startswith(known_name + " ")
            at_end = normalized_name.endswith(" " + known_name)
            # Longer canonical name contains query as a distinct word (e.g. query "apple" vs key "apple inc")
            longer = len(known_name) > len(normalized_name) and (
                known_name.startswith(normalized_name + " ")
                or known_name.endswith(" " + normalized_name)
                or f" {normalized_name} " in f" {known_name} "
            )
            if not (in_padded or at_start or at_end or longer):
                continue
            if ticker == "UNKNOWN":
                continue
            if self._us_listed_only and not self._is_us_primary_symbol(ticker):
                continue
            return ticker

        # Dynamic lookup: full public company set via Yahoo Finance
        if self._use_dynamic_lookup and requests:
            # Precision-first guard: block generic/short single-word lookups that produce
            # poisoned cache entries (e.g. "supply" → TSCO, "energy" → BE).
            single = self._tokenize_name(normalized_name)
            if len(single) == 1:
                w = single[0]
                if (
                    len(w) < 7
                    or w in self._GENERIC_SINGLE_WORD_ENTITIES
                    or w in self._ENTITY_BLOCKLIST
                ):
                    return None
            ticker = self._dynamic_lookup_company(company_name)
            if ticker and (not self._us_listed_only or self._is_us_primary_symbol(ticker)):
                if self._cache_lookups:
                    self.company_to_ticker[normalized_name] = ticker
                    self._lookup_cache[normalized_name] = ticker
                    self.ticker_to_company[ticker] = normalized_name
                    if self._cache_file:
                        self._save_lookup_cache()
                return ticker

        return None

    def get_company_for_ticker(self, ticker: str) -> Optional[str]:
        """
        Get company name for a ticker

        Args:
            ticker: Stock ticker symbol

        Returns:
            str: Company name or None
        """
        ticker_upper = ticker.upper().strip()
        return self.ticker_to_company.get(ticker_upper)

    def extract_and_map_companies(self, article: Dict, event_category: Optional[str] = None) -> Dict:
        """
        Extract companies from an article and map to tickers

        Args:
            article: Article dict with title and summary

        Returns:
            dict: Article with extracted companies and tickers
        """
        resolved_event_category = event_category or article.get("event_category")

        # Combine title and summary for searching
        full_text = article.get('title', '') + ' ' + article.get('summary', '')

        # Extract company mentions
        companies = self.extract_company_mentions(full_text, event_category=resolved_event_category)

        # Map to tickers
        candidate_entities = []
        prefiltered_rejections: List[Dict] = []
        for company in companies:
            ticker = self.get_ticker_for_company(company)
            if ticker and ticker != 'UNKNOWN':
                precheck = self._prefilter_exchange_company_match(company, ticker)
                if not precheck.get("accepted", False):
                    prefiltered_rejections.append(
                        {
                            "company": company,
                            "ticker": ticker,
                            "confidence": 'high' if company in full_text else 'medium',
                            "validation_status": "rejected",
                            "validation_reason": precheck.get("reason", "exchange verification rejected candidate"),
                            "validation_confidence": 1.0,
                            "validation_engine": "exchange_verify",
                            "validation_source": "prefilter",
                        }
                    )
                    continue
                candidate_entities.append({
                    'company': precheck.get("normalized_company", company),
                    'ticker': ticker,
                    'confidence': 'high' if company in full_text else 'medium'
                })

        # Agent-first validation (fail-closed by policy when enabled)
        mapped_entities: List[Dict] = []
        rejected_entities: List[Dict] = list(prefiltered_rejections)
        new_agent_validations_used = 0
        for candidate in candidate_entities[: self._agent_validation_max_candidates]:
            resolved_category = resolved_event_category or ""
            verdict = self._validate_candidate_by_mode(
                article=article,
                candidate=candidate,
                event_category=resolved_category,
                new_agent_validations_used=new_agent_validations_used,
            )
            if verdict.get("validation_engine") == "agent" and verdict.get("validation_source") == "new":
                new_agent_validations_used += 1
            row = {**candidate, **verdict}
            status = str(verdict.get("validation_status", "")).lower()
            if status == "approved":
                mapped_entities.append(row)
            else:
                rejected_entities.append(row)

        return {
            **article,
            'event_category': resolved_event_category,
            'extracted_companies': companies,
            'mapped_candidates': candidate_entities,
            'mapped_entities': mapped_entities,
            'rejected_entities': rejected_entities,
            'agent_validation_enabled': self._agent_validation_enabled,
            'validation_mode': self._validation_mode,
            'has_publicly_traded': len(mapped_entities) > 0
        }

    def _validate_candidate_by_mode(
        self,
        article: Dict,
        candidate: Dict,
        event_category: str,
        new_agent_validations_used: int,
    ) -> Dict:
        # Strict deterministic rule evaluation runs first in all modes.
        strict_verdict = self._validate_candidate_with_strict_rules(article, candidate, event_category)
        if strict_verdict:
            return strict_verdict

        if not self._agent_validation_enabled:
            return {
                "validation_status": "rejected",
                "validation_reason": "strict-rules mode unresolved candidate rejected",
                "validation_confidence": 0.0,
                "validation_engine": "strict_rules",
                "validation_source": "strict_fallback",
            }

        cache_key = self._validation_cache_key(article, candidate, event_category)
        cached = self._get_cached_agent_validation(cache_key)
        if isinstance(cached, dict):
            return {**cached, "validation_source": "cache"}

        if new_agent_validations_used >= self._agent_validation_max_new_per_article:
            return {
                "validation_status": "rejected",
                "validation_reason": "agent validation deferred: per-article new validation limit reached",
                "validation_confidence": 0.0,
                "validation_engine": "strict_rules",
                "validation_source": "rate_limited",
            }

        verdict = self._validate_candidate_with_agent(article, candidate, event_category)
        self._agent_validation_cache[cache_key] = {
            "cached_at": datetime.now().isoformat(),
            "verdict": verdict,
        }
        self._save_agent_validation_cache()
        return {**verdict, "validation_source": "new"}

    def _validate_candidate_with_strict_rules(
        self, article: Dict, candidate: Dict, event_category: str
    ) -> Optional[Dict]:
        """
        Deterministic per-category validations to avoid unnecessary agent calls.
        Returns a verdict only when strict rules can confidently decide.
        """
        title = str(article.get("title", "") or "")
        summary = str(article.get("summary", "") or "")
        content = f"{title} {summary}".lower()
        company = str(candidate.get("company", "") or "").strip()
        company_lower = company.lower()
        ticker = str(candidate.get("ticker", "") or "").strip().upper()

        if not company_lower or not ticker:
            return {
                "validation_status": "rejected",
                "validation_reason": "empty company or ticker",
                "validation_confidence": 1.0,
                "validation_engine": "strict_rules",
                "validation_source": "strict",
            }

        # Strong reject path for known generic tokens/homonyms.
        if company_lower in self._GENERIC_SINGLE_WORD_ENTITIES:
            return {
                "validation_status": "rejected",
                "validation_reason": f"generic single-word entity rejected: {company}",
                "validation_confidence": 1.0,
                "validation_engine": "strict_rules",
                "validation_source": "strict",
            }

        company_pat = re.escape(company_lower)
        company_mentioned = bool(re.search(rf"\b{company_pat}\b", content))
        if not company_mentioned:
            return {
                "validation_status": "rejected",
                "validation_reason": "company not explicitly mentioned in article content",
                "validation_confidence": 0.95,
                "validation_engine": "strict_rules",
                "validation_source": "strict",
            }

        universal_negation_terms = (
            "not involved",
            "no impact on",
            "not impacted",
            "unrelated to",
            "not tied to",
            "not associated with",
            "false rumor",
        )
        if any(term in content for term in universal_negation_terms):
            return {
                "validation_status": "rejected",
                "validation_reason": "explicit negation context around candidate relevance",
                "validation_confidence": 0.95,
                "validation_engine": "strict_rules",
                "validation_source": "strict",
            }

        if event_category == "product_safety_recall":
            recall_terms = (
                "recall",
                "recalled",
                "withdrawal",
                "contamination",
                "tainted",
                "do not use",
                "stop sale",
                "market withdrawal",
                "warning letter",
            )
            role_terms = (
                "manufactured by",
                "made by",
                "distributed by",
                "sold by",
                "retailer",
                "retailer of",
                "brand",
            )
            product_nouns = (
                "bean",
                "beans",
                "pickle",
                "pickles",
                "bread",
                "rice",
                "chicken",
                "bottle",
                "bottles",
                "spray",
                "vegetable",
                "ibuprofen",
                "acetaminophen",
                "syrup",
                "capsule",
                "capsules",
                "tablet",
                "tablets",
            )
            if len(company_lower.split()) == 1 and any(
                re.search(rf"\b{company_pat}(?:'s)?\s+{noun}\b", content) for noun in product_nouns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "single-word candidate appears to be product descriptor, not issuer",
                    "validation_confidence": 0.97,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            ownership_phrase = re.search(
                r"\b(manufactured by|distributed by|made by|for)\s+([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){0,3})",
                f"{title} {summary}",
            )
            if ownership_phrase:
                owner = (ownership_phrase.group(2) or "").strip().lower()
                owner_tokens = set(self._tokenize_name(owner))
                company_tokens = set(self._tokenize_name(company_lower))
                if owner_tokens and company_tokens and not owner_tokens.intersection(company_tokens):
                    retailer_context_patterns = (
                        rf"\b(at|via|through|sold at|sold by|available at|carried by)\b.{{0,60}}\b{company_pat}\b",
                        rf"\b{company_pat}\b.{{0,80}}\b(retaile?r|store(?:s)?|pharmacy|supermarket|sold|shelf|location(?:s)?)\b",
                        rf"\b{company_pat}\b.{{0,80}}\b(and|&|,)\b",
                    )
                    has_retailer_context = any(re.search(p, content) for p in retailer_context_patterns)
                    if has_retailer_context:
                        return {
                            "validation_status": "approved",
                            "validation_reason": "strict recall rule accepted co-mentioned retailer/distributor exposure context",
                            "validation_confidence": 0.86,
                            "validation_engine": "strict_rules",
                            "validation_source": "strict",
                        }
                    return {
                        "validation_status": "rejected",
                        "validation_reason": "recall article names a different manufacturer/distributor owner",
                        "validation_confidence": 0.95,
                        "validation_engine": "strict_rules",
                        "validation_source": "strict",
                    }
            if any(v in content for v in recall_terms):
                if any(v in content for v in role_terms) or re.search(
                    rf"\b{company_pat}\b.{{0,80}}\b(recall|recalled|contamination|withdrawal)\b",
                    content,
                ):
                    return {
                        "validation_status": "approved",
                        "validation_reason": "strict product recall rule matched issuer mention with recall/role context",
                        "validation_confidence": 0.92,
                        "validation_engine": "strict_rules",
                        "validation_source": "strict",
                    }
            quote_source_terms = ("analyst", "research firm", "commented", "according to")
            if any(v in content for v in quote_source_terms):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "product recall context appears commentary-only, not impacted issuer role",
                    "validation_confidence": 0.8,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "cybersecurity":
            cyber_terms = (
                "breach",
                "ransomware",
                "hack",
                "hacked",
                "incident",
                "cyberattack",
                "security incident",
                "data exposure",
                "compromised",
            )
            victim_patterns = (
                rf"\b{company_pat}\b.{{0,90}}\b(disclosed|reported|confirmed|suffered|hit by|experienced)\b.{{0,90}}\b"
                rf"(breach|incident|ransomware|cyberattack|hack|compromis)",
                rf"\b(breach|incident|ransomware|cyberattack|hack|compromis)\w*\b.{{0,40}}\b"
                rf"(at|on|hits?|targets?)\b\s+(?:the\s+)?{company_pat}\b",
            )
            quote_source_patterns = (
                rf"\b(according to|researchers? at|analysts? at|security firm)\b.{{0,60}}\b{company_pat}\b",
                rf"\b{company_pat}\b.{{0,60}}\b(said|commented|noted)\b.{{0,80}}\b(about|regarding)\b",
            )
            quote_hit = any(re.search(p, content) for p in quote_source_patterns)
            victim_hit = any(re.search(p, content) for p in victim_patterns)
            if any(v in content for v in cyber_terms) and quote_hit and not victim_hit:
                return {
                    "validation_status": "rejected",
                    "validation_reason": "cybersecurity mention appears source/commentary role, not victim role",
                    "validation_confidence": 0.85,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in cyber_terms) and victim_hit:
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict cybersecurity victim pattern matched affected issuer",
                    "validation_confidence": 0.93,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "clinical_regulatory_binary":
            clinical_terms = (
                "fda",
                "phase",
                "trial",
                "crl",
                "topline",
                "approval",
                "complete response letter",
                "clinical hold",
                "pdufa",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,90}}\b(announced|reported|received|posted|disclosed|said)\b.{{0,90}}\b"
                rf"(phase|trial|fda|approval|crl|topline|clinical hold|pdufa)",
                rf"\b(fda|food and drug administration)\b.{{0,80}}\b(issued|granted|denied|sent)\b.{{0,80}}\b(to|for)\b.{{0,40}}\b{company_pat}\b",
            )
            comparator_patterns = (
                rf"\b(compared with|versus|vs\.?|peer|competitor|alongside|including)\b.{{0,80}}\b{company_pat}\b",
            )
            if any(v in content for v in clinical_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict clinical sponsor/regulatory pattern matched affected issuer",
                    "validation_confidence": 0.93,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in clinical_terms) and any(
                re.search(p, content) for p in comparator_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "clinical mention appears comparator/peer context, not sponsor context",
                    "validation_confidence": 0.82,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "fraud_accounting_enforcement":
            fraud_terms = (
                "securities fraud",
                "accounting fraud",
                "sec charges",
                "sec alleges",
                "restatement",
                "wells notice",
                "material weakness",
                "internal control",
                "indictment",
                "criminal charges",
                "enforcement action",
                "civil complaint",
                "department of justice",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(announced|disclosed|reports?|reported|restates?|revised|agrees?|settled)\b.{{0,100}}\b"
                rf"(restatement|investigation|sec|settlement|indictment|charges|fraud|weakness)",
                rf"\b(sec|securities and exchange commission)\b.{{0,90}}\b(charges|alleges|files complaint against|announces charges against|settles with)\b.{{0,70}}\b{company_pat}\b",
                rf"\b{company_pat}\b.{{0,90}}\b(received|gets?|got)\s+a\s+wells\s+notice\b",
            )
            commentary_patterns = (
                rf"\b(according to|analyst|law firm|attorneys? for)\b.{{0,70}}\b{company_pat}\b",
            )
            if any(v in content for v in fraud_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict fraud/enforcement pattern matched subject issuer",
                    "validation_confidence": 0.91,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in fraud_terms) and any(
                re.search(p, content) for p in commentary_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "fraud/enforcement context appears commentary or third-party counsel, not subject issuer",
                    "validation_confidence": 0.82,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "supply_chain_disruption":
            supply_terms = (
                "supply chain",
                "logistics",
                "production halt",
                "plant shutdown",
                "factory",
                "shortage",
                "shipping",
                "supplier",
                "inventory",
                "port",
                "freight",
                "force majeure",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(says|said|reports?|reported|announces?|announced)\b.{{0,100}}\b"
                rf"(supply|production|shipping|shortage|disruption|halt|suspend|factory|plant|logistics)",
                rf"\b{company_pat}\b.{{0,90}}\b(halts?|suspends?|shuts?)\b.{{0,60}}\b(production|operations|plant|factory)",
                rf"(?:disruption|shortage|delay|congestion)\s+(?:at|for|in)\s+{company_pat}\b",
            )
            macro_patterns = (
                rf"\b(global supply chain|industry-wide|macroeconomic|broad market)\b.{{0,80}}\b{company_pat}\b",
            )
            if any(v in content for v in supply_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict supply-chain pattern matched affected operator/manufacturer context",
                    "validation_confidence": 0.88,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in supply_terms) and any(
                re.search(p, content) for p in macro_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "supply chain mention appears broad macro/industry commentary, not firm-specific exposure",
                    "validation_confidence": 0.78,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "financial_distress":
            distress_terms = (
                "chapter 11",
                "chapter 7",
                "bankruptcy",
                "going concern",
                "covenant breach",
                "covenant default",
                "payment default",
                "forbearance",
                "restructuring",
                "insolvency",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(files?|filed|seeks?|sought|announces?|announced|discloses?|disclosed)\b.{{0,100}}\b"
                rf"(chapter\s*11|chapter\s*7|bankruptcy|restructuring|going concern|forbearance|default)",
                rf"\b{company_pat}\b.{{0,90}}\b(covenant|liquidity|debt)\b.{{0,70}}\b(breach|default|stress|crisis|maturity)",
            )
            commentary_patterns = (
                rf"\b(credit strategist|macro|sector-wide|industry-wide)\b.{{0,80}}\b{company_pat}\b",
            )
            if any(v in content for v in distress_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict financial-distress pattern matched affected issuer",
                    "validation_confidence": 0.9,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in distress_terms) and any(
                re.search(p, content) for p in commentary_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "financial distress mention appears macro/commentary, not issuer-specific",
                    "validation_confidence": 0.8,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "dilutive_financing":
            financing_terms = (
                "secondary offering",
                "follow-on offering",
                "at-the-market",
                "atm offering",
                "registered direct offering",
                "private placement",
                "convertible notes",
                "convertible preferred",
                "warrant issuance",
                "dilution",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(announces?|announced|prices?|priced|launches?|launched|issues?|issued)\b.{{0,100}}\b"
                rf"(offering|placement|convertible|warrant|dilution|equity)",
                rf"\b{company_pat}\b.{{0,100}}\b(raises?|raised|seeks?|sought)\b.{{0,80}}\b(capital|equity|proceeds)",
            )
            agent_only_patterns = (
                rf"\b(underwriter|bookrunner|placement agent|advisor)\b.{{0,60}}\b{company_pat}\b",
            )
            if any(v in content for v in financing_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict dilutive-financing pattern matched issuing company context",
                    "validation_confidence": 0.9,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in financing_terms) and any(
                re.search(p, content) for p in agent_only_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "dilutive financing mention appears intermediary-only, not issuer subject",
                    "validation_confidence": 0.8,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "ma_corporate_action":
            ma_terms = (
                "acquisition",
                "merger agreement",
                "take-private",
                "buyout",
                "tender offer",
                "hostile bid",
                "competing bid",
                "deal termination",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(acquires?|acquired|to acquire|to be acquired|merges?|merged|announces?|announced)\b",
                rf"\b{company_pat}\b.{{0,90}}\b(tender offer|hostile bid|competing bid|deal termination|deal break)\b",
            )
            commentary_patterns = (
                rf"\b(analyst|deal talk|rumor|speculation)\b.{{0,70}}\b{company_pat}\b",
            )
            if any(v in content for v in ma_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict M&A/corporate-action pattern matched transaction party",
                    "validation_confidence": 0.89,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in ma_terms) and any(
                re.search(p, content) for p in commentary_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "M&A mention appears rumor/commentary-only, not firm transaction role",
                    "validation_confidence": 0.79,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "leadership_scandal":
            leadership_terms = (
                "ceo resigns",
                "ceo steps down",
                "cfo resigns",
                "terminated for cause",
                "executive misconduct",
                "board investigation",
                "ethics probe",
                "whistleblower complaint",
                "compliance failure",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(ceo|cfo|chairman|chief executive|chief financial officer)\b.{{0,80}}\b"
                rf"(resigns?|resigned|steps down|stepped down|terminated|fired)\b",
                rf"\b{company_pat}\b.{{0,100}}\b(board investigation|ethics probe|whistleblower complaint|executive misconduct)\b",
            )
            commentary_patterns = (
                rf"\b(commentator|analyst|expert)\b.{{0,70}}\b{company_pat}\b",
            )
            if any(v in content for v in leadership_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict leadership-scandal pattern matched issuer governance context",
                    "validation_confidence": 0.88,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in leadership_terms) and any(
                re.search(p, content) for p in commentary_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "leadership scandal mention appears commentary-only, not issuer event",
                    "validation_confidence": 0.78,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
        elif event_category == "positive_earnings_catalyst":
            earnings_terms = (
                "raised guidance",
                "guidance increased",
                "beat estimates",
                "record revenue",
                "margin expansion",
                "above consensus",
                "strong quarter",
            )
            issuer_patterns = (
                rf"\b{company_pat}\b.{{0,100}}\b(reports?|reported|posts?|posted|raises?|raised|increases?|increased|reaffirms?|reaffirmed)\b.{{0,100}}\b"
                rf"(guidance|outlook|beat|estimates|record revenue|margin expansion|consensus)",
            )
            comparator_patterns = (
                rf"\b(peer|competitor|sector|index)\b.{{0,80}}\b{company_pat}\b",
            )
            if any(v in content for v in earnings_terms) and any(
                re.search(p, content) for p in issuer_patterns
            ):
                return {
                    "validation_status": "approved",
                    "validation_reason": "strict positive-earnings pattern matched reporting issuer",
                    "validation_confidence": 0.88,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }
            if any(v in content for v in earnings_terms) and any(
                re.search(p, content) for p in comparator_patterns
            ):
                return {
                    "validation_status": "rejected",
                    "validation_reason": "positive earnings mention appears peer/comparator context",
                    "validation_confidence": 0.78,
                    "validation_engine": "strict_rules",
                    "validation_source": "strict",
                }

        return None

    def _validate_candidate_with_agent(self, article: Dict, candidate: Dict, event_category: str) -> Dict:
        """
        Validate company->ticker candidate against article semantics.

        When agent validation is enabled and fail_closed is true, any timeout/error/unavailable
        condition rejects the candidate.
        """
        if not self._agent_validation_enabled:
            return {
                "validation_status": "approved",
                "validation_reason": "agent validation disabled",
                "validation_confidence": 1.0,
                "validation_engine": "deterministic",
            }

        if not requests:
            status = "rejected" if self._agent_validation_fail_closed else "approved"
            return {
                "validation_status": status,
                "validation_reason": "requests unavailable for agent validation",
                "validation_confidence": 0.0,
                "validation_engine": "agent_unavailable",
            }
        if not self._agent_validation_endpoint:
            status = "rejected" if self._agent_validation_fail_closed else "approved"
            return {
                "validation_status": status,
                "validation_reason": "agent endpoint not configured",
                "validation_confidence": 0.0,
                "validation_engine": "agent_unavailable",
            }

        payload = {
            "validation_mode": self._validation_mode,
            "provider": self._agent_validation_provider,
            "model": self._agent_validation_model,
            "event_category": event_category,
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "url": article.get("link", article.get("url", "")),
            "candidate_company": candidate.get("company", ""),
            "candidate_ticker": candidate.get("ticker", ""),
            "instructions": (
                "Approve only when the article is clearly about this public company being affected. "
                "Reject homonyms and generic nouns (e.g., urgent, black beans)."
            ),
            "category_semantic_rules_markdown": self._CATEGORY_SEMANTIC_RULES.get(event_category, ""),
            "rubric_file": self._validation_rubric_path,
            "validation_rubric_markdown": self._validation_rubric_markdown,
        }
        headers = {"Content-Type": "application/json"}
        if self._agent_validation_api_key:
            headers["Authorization"] = f"Bearer {self._agent_validation_api_key}"

        try:
            provider = (self._agent_validation_provider or "generic_http").strip().lower()
            if provider in self._OPENAI_COMPATIBLE_PROVIDERS:
                data = self._call_openai_compatible_validation(payload=payload, headers=headers)
            else:
                resp = requests.post(
                    self._agent_validation_endpoint,
                    json=payload,
                    headers=headers,
                    timeout=self._agent_validation_timeout_seconds,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:  # Fail-closed on any agent failure.
            status = "rejected" if self._agent_validation_fail_closed else "approved"
            return {
                "validation_status": status,
                "validation_reason": f"agent validation failure: {exc}",
                "validation_confidence": 0.0,
                "validation_engine": "agent",
            }

        approved = bool(data.get("approved", False))
        reason = str(data.get("reason", "") or "").strip()
        confidence_raw = data.get("confidence", 0.0)
        try:
            confidence = float(confidence_raw)
        except (TypeError, ValueError):
            confidence = 0.0
        normalized_company = str(data.get("normalized_company_name", "") or "").strip()

        out = {
            "validation_status": "approved" if approved else "rejected",
            "validation_reason": reason or ("approved by agent" if approved else "rejected by agent"),
            "validation_confidence": confidence,
            "validation_engine": "agent",
        }
        if approved and normalized_company:
            out["company"] = normalized_company
        return out

    def _call_openai_compatible_validation(self, payload: Dict, headers: Dict) -> Dict:
        """
        Call an OpenAI-compatible chat endpoint and parse strict JSON verdict.
        """
        if not self._agent_validation_model:
            raise ValueError("agent model is required for openai-compatible provider")

        system_prompt = (
            "You validate entity-to-ticker relevance for investment event triage. "
            "Return ONLY JSON with keys: approved (bool), confidence (0..1), reason (string), "
            "normalized_company_name (string, optional)."
        )
        user_prompt = (
            "Apply the provided markdown rubric and category rules. "
            "Reject homonyms/generic nouns and approve only direct, clearly affected issuers.\n\n"
            f"Rubric file: {payload.get('rubric_file', '')}\n"
            f"Rubric markdown:\n{payload.get('validation_rubric_markdown', '')}\n\n"
            f"Category semantic rules:\n{payload.get('category_semantic_rules_markdown', '')}\n\n"
            "Candidate payload JSON:\n"
            f"{json.dumps(payload, ensure_ascii=True)}"
        )
        body = {
            "model": self._agent_validation_model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        resp = requests.post(
            self._agent_validation_endpoint,
            json=body,
            headers=headers,
            timeout=self._agent_validation_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json()
        content = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        if isinstance(content, list):
            content = "".join(str(x.get("text", "")) for x in content if isinstance(x, dict))
        raw = str(content or "").strip()
        parsed = self._parse_json_object(raw)
        if not isinstance(parsed, dict):
            raise ValueError("openai-compatible response missing JSON verdict")
        return parsed

    @staticmethod
    def _parse_json_object(value: str) -> Optional[Dict]:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
        if fence:
            try:
                obj = json.loads(fence.group(1))
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                return None

        brace = re.search(r"(\{.*\})", text, flags=re.DOTALL)
        if brace:
            try:
                obj = json.loads(brace.group(1))
                if isinstance(obj, dict):
                    return obj
            except json.JSONDecodeError:
                return None
        return None

    def batch_extract(self, articles: List[Dict], event_category: Optional[str] = None) -> List[Dict]:
        """
        Extract entities from multiple articles

        Args:
            articles: List of article dictionaries

        Returns:
            list: Articles with extracted entities
        """
        results = []
        for article in articles:
            article_event_category = event_category or article.get("event_category")
            results.append(self.extract_and_map_companies(article, event_category=article_event_category))
        return results

    def get_ticker_mentions(self, articles: List[Dict]) -> Dict[str, int]:
        """
        Get count of how many times each ticker appears in articles

        Args:
            articles: Processed articles with mapped entities

        Returns:
            dict: Ticker -> mention count
        """
        ticker_counts = {}

        for article in articles:
            for entity in article.get('mapped_entities', []):
                ticker = entity.get('ticker')
                if ticker:
                    ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

        return ticker_counts

    def get_most_mentioned_companies(self, articles: List[Dict], limit: int = 10) -> List[Tuple[str, str, int]]:
        """
        Get most frequently mentioned companies in articles

        Args:
            articles: Processed articles with mapped entities
            limit: Number of results to return

        Returns:
            list: Tuples of (company_name, ticker, mention_count)
        """
        ticker_counts = self.get_ticker_mentions(articles)

        results = []
        for ticker, count in sorted(ticker_counts.items(), key=lambda x: x[1], reverse=True)[:limit]:
            company_name = self.get_company_for_ticker(ticker)
            results.append((company_name or ticker, ticker, count))

        return results

    def unlisted_mentions(self, article: Dict) -> List[str]:
        """Names extracted from text that did not resolve to a mapped public ticker."""
        mapped_lower = {m.get("company", "").strip().lower() for m in article.get("mapped_entities", [])}
        out: List[str] = []
        for c in article.get("extracted_companies") or []:
            key = (c or "").strip().lower()
            if key and key not in mapped_lower:
                out.append(c)
        return out

    def display_scan_preview(self, articles: List[Dict], max_articles: int = 15) -> None:
        """
        After a news scan: show each article with public tickers and other extracted names.
        """
        print("\nArticles with extracted names (public tickers + other mentions)")
        print("-" * 80)
        n_pub = sum(1 for a in articles if a.get("has_publicly_traded"))
        print(
            f"Summary: {len(articles)} articles — {n_pub} with at least one US-listed ticker, "
            f"{len(articles) - n_pub} with none from extraction.\n"
        )
        for i, article in enumerate(articles[:max_articles], 1):
            print(f"{i}. {article.get('title', 'No title')}")
            print(f"   Source: {article.get('source')}  |  category: {article.get('event_category', 'n/a')}")
            mapped = article.get("mapped_entities") or []
            if mapped:
                pub = ", ".join(f"{m.get('company')} ({m.get('ticker')})" for m in mapped)
                print(f"   US-listed (NYSE/Nasdaq-style): {pub}")
            else:
                print("   US-listed (NYSE/Nasdaq-style): (none from this headline)")
            other = self.unlisted_mentions(article)
            if other:
                print(f"   Other mentions (no listed ticker in our map): {', '.join(other)}")
            elif not mapped:
                print("   Other mentions: (none extracted)")
            print()
        if len(articles) > max_articles:
            print(f"… and {len(articles) - max_articles} more articles (run full analysis to process all).\n")

    def display_extraction_results(self, articles: List[Dict]) -> None:
        """
        Display extraction results in readable format

        Args:
            articles: Articles with extracted entities
        """
        print("\nEXTRACTED ENTITIES")
        print("="*80)

        publicly_traded_count = sum(1 for a in articles if a.get('has_publicly_traded'))
        print(f"Articles with US-listed tickers: {publicly_traded_count}/{len(articles)}\n")

        # Show most mentioned companies
        most_mentioned = self.get_most_mentioned_companies(articles)
        if most_mentioned:
            print("Most Mentioned Companies:")
            print("-"*40)
            for i, (company, ticker, count) in enumerate(most_mentioned, 1):
                print(f"{i}. {company} ({ticker}): {count} mentions")
        else:
            print("No US-listed tickers found in articles")

        # Show articles with entities
        print("\n" + "="*80)
        for i, article in enumerate(articles[:5], 1):
            print(f"\n{i}. {article.get('title')}")
            if article.get('mapped_entities'):
                print("   Listed (ticker):")
                for entity in article.get('mapped_entities', []):
                    print(f"     - {entity.get('company')} ({entity.get('ticker')})")
            else:
                print("   Listed (ticker): (none)")
            other = self.unlisted_mentions(article)
            if other:
                print(f"   Other mentions: {', '.join(other)}")


def main():
    """Test the extractor"""
    extractor = EntityExtractor()

    # Test articles
    test_articles = [
        {
            'title': 'Apple Inc. Announces Major Security Breach',
            'summary': 'Apple has confirmed a data breach affecting customer accounts...',
            'source': 'test',
            'link': 'test.com'
        },
        {
            'title': 'Microsoft Corporation Responds to Cyberattack',
            'summary': 'Microsoft stated that the attack was contained quickly...',
            'source': 'test',
            'link': 'test.com'
        },
        {
            'title': 'JPMorgan Chase Investigates Incident',
            'summary': 'The bank confirmed a security incident affecting...',
            'source': 'test',
            'link': 'test.com'
        },
    ]

    # Extract entities
    processed = extractor.batch_extract(test_articles)

    # Display results
    extractor.display_extraction_results(processed)


if __name__ == '__main__':
    main()
