"""
Materiality extraction enricher.

Extracts quantitative severity signals from article title/summary text and
returns them as structured fields the impact triage scorer can consume:

- `materiality_usd`: dollar exposure / loss / fine / issuance amount
- `materiality_pct_revenue`: percent-of-revenue framing (e.g. "5% of revenue")
- `materiality_unit_count`: number of impacted records / units / customers

Two layers, matching the plan's cascade policy:

1. Deterministic regex extraction (always on).
2. Optional LLM refinement (last resort) via `llm_client.LLMClient` with the
   usual budget caps. Deterministic output stands when the client abstains.

All downstream scoring remains deterministic given these fields; the LLM is
only an *optional* signal enricher.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

try:
    from llm_client import LLMClient
except ImportError:  # pragma: no cover - llm_client ships with this repo
    LLMClient = None  # type: ignore[assignment]


_USD_UNIT_MULTIPLIERS = {
    "k": 1_000.0,
    "thousand": 1_000.0,
    "m": 1_000_000.0,
    "mm": 1_000_000.0,
    "mn": 1_000_000.0,
    "million": 1_000_000.0,
    "b": 1_000_000_000.0,
    "bn": 1_000_000_000.0,
    "billion": 1_000_000_000.0,
    "t": 1_000_000_000_000.0,
    "trillion": 1_000_000_000_000.0,
}


_USD_RE = re.compile(
    r"""
    \$\s*
    (?P<amount>\d+(?:[,.]\d+)*)
    \s*
    (?P<unit>
        k|thousand|m|mm|mn|million|b|bn|billion|t|trillion
    )?
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Also match "5 million", "$5B", "5 billion dollars" forms without leading $.
_AMOUNT_WORD_RE = re.compile(
    r"""
    (?P<amount>\d+(?:[,.]\d+)*)
    \s*
    (?P<unit>million|billion|trillion|thousand)
    \s*
    (?:dollars|usd)
    """,
    re.IGNORECASE | re.VERBOSE,
)


_PCT_REVENUE_RE = re.compile(
    r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*(?:of|of\s+(?:annual\s+)?revenue|of\s+sales)",
    re.IGNORECASE,
)


_UNIT_COUNT_RE = re.compile(
    r"""
    (?P<amount>\d+(?:[,.]\d+)*)
    \s*
    (?P<unit>million|billion|thousand)?
    \s*
    (?P<noun>
        records|customers|users|accounts|patients|vehicles|units|devices|employees
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _amount_to_float(amount: str, unit: Optional[str]) -> Optional[float]:
    try:
        # Assume US-style grouping: commas are thousands.
        clean = amount.replace(",", "")
        value = float(clean)
    except (TypeError, ValueError):
        return None
    if unit:
        multiplier = _USD_UNIT_MULTIPLIERS.get(unit.lower())
        if multiplier:
            value *= multiplier
    return value


def _max_usd(text: str) -> Optional[float]:
    if not text:
        return None
    best: Optional[float] = None
    for match in _USD_RE.finditer(text):
        value = _amount_to_float(match.group("amount"), match.group("unit"))
        if value is not None and (best is None or value > best):
            best = value
    for match in _AMOUNT_WORD_RE.finditer(text):
        value = _amount_to_float(match.group("amount"), match.group("unit"))
        if value is not None and (best is None or value > best):
            best = value
    return best


def _max_pct_revenue(text: str) -> Optional[float]:
    if not text:
        return None
    best: Optional[float] = None
    for match in _PCT_REVENUE_RE.finditer(text):
        try:
            pct = float(match.group("pct"))
        except (TypeError, ValueError):
            continue
        if best is None or pct > best:
            best = pct
    return best


def _max_unit_count(text: str) -> Optional[int]:
    if not text:
        return None
    best: Optional[float] = None
    for match in _UNIT_COUNT_RE.finditer(text):
        value = _amount_to_float(match.group("amount"), match.group("unit"))
        if value is None:
            continue
        if best is None or value > best:
            best = value
    if best is None:
        return None
    return int(best)


@dataclass
class MaterialityResult:
    materiality_usd: Optional[float] = None
    materiality_pct_revenue: Optional[float] = None
    materiality_unit_count: Optional[int] = None
    engine: str = "deterministic"
    reasons: List[str] = field(default_factory=list)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "materiality_usd": self.materiality_usd,
            "materiality_pct_revenue": self.materiality_pct_revenue,
            "materiality_unit_count": self.materiality_unit_count,
            "materiality_engine": self.engine,
            "materiality_reasons": list(self.reasons),
        }


def extract(
    article: Dict[str, Any],
    *,
    llm_client: Optional["LLMClient"] = None,
) -> MaterialityResult:
    """
    Extract materiality fields from an article. LLM path is opt-in and budget-gated.
    """
    title = str(article.get("title", "") or "")
    summary = str(article.get("summary", "") or "")
    text = f"{title}\n{summary}"

    usd = _max_usd(text)
    pct = _max_pct_revenue(text)
    units = _max_unit_count(text)
    reasons: List[str] = []
    if usd is not None:
        reasons.append(f"USD exposure signal: ${usd:,.0f}")
    if pct is not None:
        reasons.append(f"% of revenue signal: {pct:.1f}%")
    if units is not None:
        reasons.append(f"Unit/record count signal: {units:,}")

    result = MaterialityResult(
        materiality_usd=usd,
        materiality_pct_revenue=pct,
        materiality_unit_count=units,
        reasons=reasons,
    )

    # Only consult the LLM when the deterministic pass extracted nothing and a
    # client is available. This guarantees the vast majority of articles never
    # touch the paid path.
    if llm_client is None:
        return result
    if usd is not None or pct is not None or units is not None:
        return result

    try:
        distress_score = int(article.get("distress_score") or 0)
    except (TypeError, ValueError):
        distress_score = 0

    payload = {
        "title": title,
        "summary": summary,
        "event_category": article.get("event_category", ""),
    }
    llm_result = llm_client.call(
        module="materiality",
        prompt_key="materiality_v1",
        prompt_payload=payload,
        event_category=str(article.get("event_category", "") or ""),
        distress_score=distress_score,
    )
    if not llm_result.used_llm or not isinstance(llm_result.data, dict):
        return result

    data = llm_result.data
    result.engine = "agent"
    result.reasons.append("LLM materiality extraction")
    try:
        result.materiality_usd = (
            float(data["materiality_usd"]) if data.get("materiality_usd") is not None else usd
        )
    except (TypeError, ValueError):
        pass
    try:
        result.materiality_pct_revenue = (
            float(data["materiality_pct_revenue"])
            if data.get("materiality_pct_revenue") is not None
            else pct
        )
    except (TypeError, ValueError):
        pass
    try:
        result.materiality_unit_count = (
            int(data["materiality_unit_count"])
            if data.get("materiality_unit_count") is not None
            else units
        )
    except (TypeError, ValueError):
        pass

    return result


def materiality_impact_bonus(result: MaterialityResult) -> int:
    """
    Convert structured materiality into a conservative additive score for the
    impact triage. Deliberately bounded so no single heuristic dominates.

    Bonus tiers (max 18 total):
    - USD exposure
      - >= $10B: +10
      - >= $1B:  +7
      - >= $100M: +5
      - >= $10M:  +3
    - % revenue
      - >= 20%: +6
      - >= 10%: +4
      - >= 3%:  +2
    - Unit count
      - >= 10M:   +4
      - >= 1M:    +2
      - >= 100k:  +1
    """
    bonus = 0
    if result.materiality_usd is not None:
        value = float(result.materiality_usd)
        if value >= 10_000_000_000:
            bonus += 10
        elif value >= 1_000_000_000:
            bonus += 7
        elif value >= 100_000_000:
            bonus += 5
        elif value >= 10_000_000:
            bonus += 3
    if result.materiality_pct_revenue is not None:
        pct = float(result.materiality_pct_revenue)
        if pct >= 20.0:
            bonus += 6
        elif pct >= 10.0:
            bonus += 4
        elif pct >= 3.0:
            bonus += 2
    if result.materiality_unit_count is not None:
        count = int(result.materiality_unit_count)
        if count >= 10_000_000:
            bonus += 4
        elif count >= 1_000_000:
            bonus += 2
        elif count >= 100_000:
            bonus += 1
    return min(bonus, 18)


__all__ = [
    "MaterialityResult",
    "extract",
    "materiality_impact_bonus",
]
