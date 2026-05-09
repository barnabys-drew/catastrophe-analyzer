"""
Ripple Extractor — maps private-company catastrophe events to publicly traded sector proxies.

When CA detects an event at a private company (hospital, university, SaaS startup, etc.),
the entity validation gate drops it because no ticker exists. This module intercepts those
articles and returns sector-proxy candidates so the rest of the pipeline can still fire a signal.

Each mapping returns 1-3 candidates shaped identically to validated entity candidates:
  {"ticker": "PANW", "company": "Palo Alto Networks", "confidence": "medium", "validation_status": "approved", "ripple": True}
"""

from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# Category → sector proxy mappings
# Each entry: (ticker, company_name, signal_direction_hint)
# direction_hint is informational only — signal_generator owns the final direction
# ---------------------------------------------------------------------------

_CATEGORY_PROXIES: Dict[str, List[Dict]] = {
    # Cybersecurity breach / ransomware at victim → defensive cyber stocks benefit
    "cybersecurity": [
        {"ticker": "PANW", "company": "Palo Alto Networks",  "confidence": "medium"},
        {"ticker": "CRWD", "company": "CrowdStrike",         "confidence": "medium"},
        {"ticker": "ZS",   "company": "Zscaler",             "confidence": "low"},
    ],
    "data_breach": [
        {"ticker": "PANW", "company": "Palo Alto Networks",  "confidence": "medium"},
        {"ticker": "CRWD", "company": "CrowdStrike",         "confidence": "medium"},
        {"ticker": "OKTA", "company": "Okta",                "confidence": "low"},
    ],
    "ransomware": [
        {"ticker": "CRWD", "company": "CrowdStrike",         "confidence": "high"},
        {"ticker": "PANW", "company": "Palo Alto Networks",  "confidence": "medium"},
        {"ticker": "S",    "company": "SentinelOne",         "confidence": "low"},
    ],

    # Healthcare / hospital incidents → hospital operators + health IT
    "healthcare_incident": [
        {"ticker": "CYH",  "company": "Community Health Systems", "confidence": "medium"},
        {"ticker": "THC",  "company": "Tenet Healthcare",         "confidence": "medium"},
        {"ticker": "HCA",  "company": "HCA Healthcare",           "confidence": "low"},
    ],

    # Food safety / product recall → publicly traded food chains + distributors
    "product_safety_recall": [
        {"ticker": "SFM",  "company": "Sprouts Farmers Market",   "confidence": "medium"},
        {"ticker": "KR",   "company": "Kroger",                   "confidence": "medium"},
        {"ticker": "SYY",  "company": "Sysco",                    "confidence": "low"},
    ],

    # Supply chain disruption → logistics + freight
    "supply_chain": [
        {"ticker": "FDX",  "company": "FedEx",                    "confidence": "medium"},
        {"ticker": "UPS",  "company": "UPS",                      "confidence": "medium"},
        {"ticker": "XPO",  "company": "XPO",                      "confidence": "low"},
    ],
    # Alias for CA's actual taxonomy key
    "supply_chain_disruption": [
        {"ticker": "FDX",  "company": "FedEx",                    "confidence": "medium"},
        {"ticker": "UPS",  "company": "UPS",                      "confidence": "medium"},
        {"ticker": "XPO",  "company": "XPO",                      "confidence": "low"},
    ],

    # Financial distress at private firms → regional bank exposure
    "financial_distress": [
        {"ticker": "KRE",  "company": "SPDR S&P Regional Banking ETF", "confidence": "medium"},
        {"ticker": "JPM",  "company": "JPMorgan Chase",                "confidence": "low"},
    ],

    # Geopolitical / government action → defense
    "geo_crisis": [
        {"ticker": "LMT",  "company": "Lockheed Martin",         "confidence": "medium"},
        {"ticker": "RTX",  "company": "Raytheon Technologies",   "confidence": "medium"},
        {"ticker": "NOC",  "company": "Northrop Grumman",        "confidence": "low"},
    ],
    "political_shock": [
        {"ticker": "LMT",  "company": "Lockheed Martin",         "confidence": "medium"},
        {"ticker": "GLD",  "company": "SPDR Gold Shares ETF",    "confidence": "medium"},
    ],
    # Alias for CA's actual taxonomy key
    "geopolitical_sanctions_exposure": [
        {"ticker": "LMT",  "company": "Lockheed Martin",         "confidence": "medium"},
        {"ticker": "RTX",  "company": "Raytheon Technologies",   "confidence": "medium"},
        {"ticker": "GLD",  "company": "SPDR Gold Shares ETF",    "confidence": "low"},
    ],

    # Infrastructure / utility outages
    "infrastructure_failure": [
        {"ticker": "NEE",  "company": "NextEra Energy",          "confidence": "low"},
        {"ticker": "DUK",  "company": "Duke Energy",             "confidence": "low"},
    ],

    # Environmental / industrial accident
    "environmental_incident": [
        {"ticker": "CLF",  "company": "Cleveland-Cliffs",        "confidence": "low"},
        {"ticker": "ECL",  "company": "Ecolab",                  "confidence": "medium"},
    ],

    # Leadership / fraud at private company → broader sector sentiment
    "leadership_scandal": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
    ],
    "fraud_accounting_enforcement": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
        {"ticker": "XLF",  "company": "Financial Sector ETF",    "confidence": "low"},
    ],

    # Biotech FDA/clinical decision → biotech sector ETFs
    "clinical_regulatory_binary": [
        {"ticker": "XBI",  "company": "SPDR S&P Biotech ETF",    "confidence": "medium"},
        {"ticker": "IBB",  "company": "iShares Biotech ETF",     "confidence": "medium"},
    ],

    # Equity dilution at private firm → sector ETF, generally negative for sector
    "dilutive_financing": [
        {"ticker": "IWM",  "company": "Russell 2000 ETF",        "confidence": "low"},
    ],

    # M&A activity → sector ETFs (target sector usually moves)
    "ma_corporate_action": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
        {"ticker": "IWM",  "company": "Russell 2000 ETF",        "confidence": "low"},
    ],

    # Earnings catalyst at private firm — broad market sector signal
    "positive_earnings_catalyst": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
    ],
    "negative_earnings_catalyst": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
    ],

    # Short-seller report — typically tech/growth pressure
    "short_seller_report": [
        {"ticker": "QQQ",  "company": "Invesco QQQ Trust",       "confidence": "low"},
        {"ticker": "ARKK", "company": "ARK Innovation ETF",      "confidence": "low"},
    ],

    # Credit rating downgrade/upgrade → bond ETFs + financials
    "credit_rating_action": [
        {"ticker": "TLT",  "company": "iShares 20+ Year Treasury", "confidence": "medium"},
        {"ticker": "LQD",  "company": "iShares Investment Grade Corp Bond", "confidence": "medium"},
    ],

    # Going-concern audit warning — financial-sector negative signal
    "going_concern_auditor_change": [
        {"ticker": "XLF",  "company": "Financial Sector ETF",    "confidence": "low"},
    ],

    # Guidance cut at peer — sector-broad negative
    "guidance_cut_preannouncement": [
        {"ticker": "SPY",  "company": "S&P 500 ETF",             "confidence": "low"},
    ],

    # Securities class action — broad market caution
    "securities_class_action": [
        {"ticker": "XLF",  "company": "Financial Sector ETF",    "confidence": "low"},
    ],

    # Labor strike/action — sector-specific (auto, transport, hospitality)
    "labor_action": [
        {"ticker": "XLI",  "company": "Industrial Sector ETF",   "confidence": "medium"},
        {"ticker": "IYT",  "company": "iShares Transportation",  "confidence": "low"},
    ],

    # Activist filing (13D) — small-cap volatility, often rerates the target's sector
    "activist_13d_filing": [
        {"ticker": "IWM",  "company": "Russell 2000 ETF",        "confidence": "low"},
        {"ticker": "MDY",  "company": "S&P MidCap 400 ETF",      "confidence": "low"},
    ],
}

# Keyword → category overrides for title-based refinement
_TITLE_KEYWORD_OVERRIDES: List[tuple] = [
    (["ransomware", "encrypt", "extort"],                "ransomware"),
    (["breach", "hack", "intrusion", "leaked", "stolen data"], "data_breach"),
    (["hospital", "health system", "clinic", "medical center"], "healthcare_incident"),
    (["recall", "contamination", "fda warning", "salmonella", "listeria"], "product_safety_recall"),
    (["supply chain", "port", "shipping", "freight"],    "supply_chain"),
    (["sanction", "airstrike", "military", "conflict"],  "geo_crisis"),
    (["fraud", "accounting", "sec charges", "misstatement"], "fraud_accounting_enforcement"),
]


def get_sector_proxies(article: Dict, max_proxies: int = 2) -> List[Dict]:
    """
    Return sector-proxy mapped_candidates for a private-company article.

    Args:
        article: the article dict (needs 'event_category', 'title', 'summary')
        max_proxies: cap the number of candidates returned (default 2)

    Returns:
        List of candidate dicts with validation_status='approved' and ripple=True,
        or [] if no mapping exists for this category.
    """
    event_category = (article.get("event_category") or "").lower()
    title = (article.get("title") or "").lower()
    summary = (article.get("summary") or "").lower()
    text = title + " " + summary

    # Try keyword override first for precise category detection
    resolved_category = event_category
    for keywords, override_cat in _TITLE_KEYWORD_OVERRIDES:
        if any(kw in text for kw in keywords):
            resolved_category = override_cat
            break

    proxies = _CATEGORY_PROXIES.get(resolved_category) or _CATEGORY_PROXIES.get(event_category)
    if not proxies:
        return []

    return [
        {
            "ticker":            p["ticker"],
            "company":           p["company"],
            "confidence":        p["confidence"],
            "validation_status": "approved",
            "ripple":            True,
            "ripple_source_category": resolved_category,
        }
        for p in proxies[:max_proxies]
    ]


def enrich_with_ripple(article: Dict, max_proxies: int = 2) -> Optional[Dict]:
    """
    If the article has no publicly traded entity, attempt to add ripple proxies.
    Returns a modified copy of the article with has_publicly_traded=True and
    mapped_candidates populated, or None if no proxies apply.
    """
    proxies = get_sector_proxies(article, max_proxies=max_proxies)
    if not proxies:
        return None

    enriched = dict(article)
    enriched["mapped_candidates"] = proxies
    enriched["mapped_entities"] = proxies
    enriched["has_publicly_traded"] = True
    enriched["ripple_enriched"] = True
    return enriched
