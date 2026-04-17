"""
Signal freshness guardrail (pre-alert enricher).

Purpose:
Right before an alert goes out, check whether a newer headline materially
changes the event. For example, the original event might have been "FDA issues
complete response letter" and a newer headline might be "FDA rescinds CRL and
approves drug." The guardrail blocks or modifies the alert when the new context
contradicts the original signal.

Design:
- Deterministic first pass using keyword reversals per category.
- Optional LLM refinement (last resort) gated by `llm_client.LLMClient`.
- Returns a structured `FreshnessVerdict` that alerting layers inspect before
  sending. Callers must be safe to ignore the verdict (fail-open) when the
  guardrail is disabled or errors, so the pipeline stays deterministic.

Stale-news handling is also covered here: articles older than
`max_article_age_hours_for_alert` suppress the alert unless explicitly allowed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:
    from llm_client import LLMClient
except ImportError:  # pragma: no cover - llm_client ships with this repo
    LLMClient = None  # type: ignore[assignment]


# Category-specific "reversal" cues that invert the original event narrative.
# If any of these appear in the latest headlines within the freshness window
# *and* the original event was not already the positive framing, the alert is
# blocked and the caller is notified via `FreshnessVerdict`.
_REVERSALS: Dict[str, List[str]] = {
    "cybersecurity": [
        "services restored",
        "no evidence of exfiltration",
        "no customer data accessed",
        "contained the incident",
        "no impact on operations",
    ],
    "clinical_regulatory_binary": [
        "fda approval",
        "approved by the fda",
        "met primary endpoint",
        "positive topline",
        "approves drug",
        "approves therapy",
        "approves the drug",
        "priority review granted",
    ],
    "product_safety_recall": [
        "recall withdrawn",
        "recall lifted",
        "safety concerns addressed",
        "cleared to resume",
    ],
    "fraud_accounting_enforcement": [
        "charges dismissed",
        "case dismissed",
        "no findings of fraud",
        "terminated investigation",
        "settled without admitting",
    ],
    "supply_chain_disruption": [
        "resumes production",
        "resumed operations",
        "shortage eased",
        "full capacity restored",
    ],
    "financial_distress": [
        "refinancing completed",
        "covenant waiver",
        "liquidity improved",
        "emerges from chapter 11",
    ],
    "dilutive_financing": [
        "withdraws offering",
        "withdrew offering",
        "cancels offering",
        "oversubscribed",
    ],
    "ma_corporate_action": [
        "deal termination",
        "deal break",
        "abandons merger",
        "walks away",
    ],
    "leadership_scandal": [
        "reinstated",
        "cleared of wrongdoing",
        "no wrongdoing found",
        "no basis for the allegations",
    ],
    "positive_earnings_catalyst": [
        "withdraws guidance",
        "earnings miss",
        "profit warning",
        "guidance cut",
    ],
    "geopolitical_sanctions_exposure": [
        "sanctions lifted",
        "license granted",
        "delisted from entity list",
        "export ban lifted",
    ],
    "negative_earnings_catalyst": [
        "raises guidance",
        "beats estimates",
        "raised guidance",
        "record revenue",
    ],
    "short_seller_report": [
        "company denies",
        "rebuttal",
        "independent review found no",
        "short report withdrawn",
    ],
    "credit_rating_action": [
        "upgraded",
        "outlook revised to positive",
        "outlook stable",
        "affirmed rating",
    ],
    "going_concern_auditor_change": [
        "going concern removed",
        "reinstated audit opinion",
        "refinancing completed",
    ],
    "guidance_cut_preannouncement": [
        "raises guidance",
        "reaffirmed guidance",
        "better-than-expected",
    ],
    "activist_13d_filing": [
        "settlement reached",
        "cooperation agreement",
        "withdraw nomination",
    ],
    "labor_action": [
        "strike ends",
        "tentative agreement",
        "ratifies contract",
        "ratified contract",
        "returns to work",
    ],
    "securities_class_action": [
        "motion to dismiss granted",
        "dismissed with prejudice",
    ],
    "insider_trading_cluster": [
        "10b5-1 plan",
        "rule 10b5-1",
        "scheduled sale",
    ],
}


@dataclass
class FreshnessVerdict:
    allow_alert: bool = True
    reason: str = ""
    evidence: List[str] = field(default_factory=list)
    engine: str = "deterministic"
    stale: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "allow_alert": self.allow_alert,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "engine": self.engine,
            "stale": self.stale,
        }


def _parse_dt(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    if text.endswith("Z"):
        try:
            dt = datetime.strptime(text[:-1], "%Y-%m-%dT%H:%M:%S")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _deterministic_reversal(event_category: str, candidate_text: str) -> List[str]:
    """Return reversal phrases found in `candidate_text` for the given category."""
    markers = _REVERSALS.get(event_category, [])
    text = candidate_text.lower()
    return [m for m in markers if m in text]


def evaluate(
    *,
    event: Dict[str, Any],
    recent_headlines: Sequence[Dict[str, Any]],
    now: Optional[datetime] = None,
    max_article_age_hours: int = 72,
    freshness_window_hours: int = 24,
    llm_client: Optional["LLMClient"] = None,
) -> FreshnessVerdict:
    """
    Evaluate whether an alert for `event` should proceed.

    Parameters
    ----------
    event
        Watch/triage record with at least `event_category`, `event_date`,
        `ticker`, and (optional) `title`, `summary`, `last_seen_at`.
    recent_headlines
        Newer headlines for the same ticker / category that arrived after the
        original event. Each must have a `title`, `summary`, and `published`.
    now
        Optional clock override for tests.
    max_article_age_hours
        Articles older than this are considered stale and suppress the alert.
    freshness_window_hours
        Only headlines within this window relative to `now` are consulted when
        checking for reversals.
    llm_client
        Optional shared LLMClient. When the deterministic pass finds no
        reversal but the caller wants extra precision on high-distress events,
        the client may be consulted. Budget gates still apply.
    """
    now_dt = now or datetime.now(timezone.utc)
    event_category = str(event.get("event_category", "") or "")

    # Stale-news check on the originating article.
    event_time = _parse_dt(event.get("published")) or _parse_dt(event.get("event_date"))
    if event_time is not None and max_article_age_hours > 0:
        age = now_dt - event_time
        if age > timedelta(hours=max_article_age_hours):
            return FreshnessVerdict(
                allow_alert=False,
                reason=f"stale_article:{int(age.total_seconds()//3600)}h>{max_article_age_hours}h",
                stale=True,
            )

    # Deterministic reversal check on newer headlines.
    reversal_hits: List[str] = []
    window_start = now_dt - timedelta(hours=max(0, freshness_window_hours))
    for headline in recent_headlines:
        pub = _parse_dt(headline.get("published"))
        if pub is not None and pub < window_start:
            continue
        text = f"{headline.get('title', '')} {headline.get('summary', '')}"
        hits = _deterministic_reversal(event_category, text)
        reversal_hits.extend(hits)

    if reversal_hits:
        return FreshnessVerdict(
            allow_alert=False,
            reason="reversal_detected",
            evidence=sorted(set(reversal_hits)),
            engine="deterministic",
        )

    # Optional LLM refinement: only if a client is available AND distress is
    # high enough to justify the cost. The LLMClient enforces the distress
    # gate already, but we skip the call entirely when the cascade would skip.
    if llm_client is None:
        return FreshnessVerdict(allow_alert=True, engine="deterministic")

    try:
        distress_score = int(event.get("distress_score") or 0)
    except (TypeError, ValueError):
        distress_score = 0

    payload = {
        "event_category": event_category,
        "event_title": event.get("title", ""),
        "event_summary": event.get("summary", ""),
        "recent_headlines": [
            {
                "title": h.get("title", ""),
                "summary": h.get("summary", ""),
                "published": str(h.get("published", "")),
            }
            for h in recent_headlines
        ],
    }
    result = llm_client.call(
        module="freshness_guardrail",
        prompt_key="freshness_v1",
        prompt_payload=payload,
        event_category=event_category,
        distress_score=distress_score,
    )
    if not result.used_llm or not isinstance(result.data, dict):
        return FreshnessVerdict(allow_alert=True, engine="deterministic")

    data = result.data
    allow = bool(data.get("allow_alert", True))
    reason = str(data.get("reason", "llm_ok" if allow else "llm_blocked"))
    evidence = data.get("evidence", [])
    if not isinstance(evidence, list):
        evidence = []
    return FreshnessVerdict(
        allow_alert=allow,
        reason=reason,
        evidence=[str(e) for e in evidence[:8]],
        engine="agent",
    )


__all__ = ["FreshnessVerdict", "evaluate"]
