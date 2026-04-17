"""
Impact triage module.

Computes event impact likelihood using:
1) deterministic scoring (always available)
2) optional agent/LLM HTTP provider with deterministic fallback

The agent path routes through `llm_client.LLMClient` so that the cost-control
cascade (cache -> budget -> provider) and accounting ledger apply uniformly
across every enricher.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from text_match import keyword_in_text

try:
    import requests
except ImportError:  # pragma: no cover - requests exists in project deps
    requests = None

try:
    from llm_client import LLMClient, DECISION_USED, DECISION_CACHE_HIT
except ImportError:  # pragma: no cover - llm_client ships with this repo
    LLMClient = None  # type: ignore[assignment]
    DECISION_USED = "used"
    DECISION_CACHE_HIT = "cached"

try:
    from materiality_extraction import extract as _extract_materiality
    from materiality_extraction import materiality_impact_bonus
except ImportError:  # pragma: no cover - module ships with this repo
    _extract_materiality = None  # type: ignore[assignment]
    def materiality_impact_bonus(_result):  # type: ignore[no-redef]
        return 0


@dataclass
class ImpactTriageResult:
    impact_score: int
    impact_likelihood: str
    impact_summary: str
    triage_engine: str
    reasons: List[str]

    def as_dict(self) -> Dict:
        return {
            "impact_score": self.impact_score,
            "impact_likelihood": self.impact_likelihood,
            "impact_summary": self.impact_summary,
            "triage_engine": self.triage_engine,
            "reasons": self.reasons,
        }


class ImpactTriage:
    """Deterministic + optional agent-assisted impact triage."""

    def __init__(
        self,
        config: Optional[Dict] = None,
        llm_client: Optional["LLMClient"] = None,
    ):
        cfg = config or {}
        triage_cfg = cfg.get("triage", {})
        self.enabled = bool(triage_cfg.get("enabled", True))
        self.agent_enabled = bool(triage_cfg.get("agent_enabled", False))
        self.fallback_to_deterministic = bool(triage_cfg.get("fallback_to_deterministic", True))
        self.agent_timeout_seconds = int(triage_cfg.get("agent_timeout_seconds", 8))
        self.agent_endpoint = (triage_cfg.get("agent_endpoint") or "").strip()
        self.agent_api_key = (triage_cfg.get("agent_api_key") or "").strip()
        self.agent_provider = str(triage_cfg.get("agent_provider") or "generic_http").strip()
        self.agent_model = str(triage_cfg.get("agent_model") or "").strip()
        # Optional shared LLM client; ImpactTriage always maintains deterministic
        # fallback so `llm_client=None` is a valid configuration.
        self._llm_client = llm_client

    @staticmethod
    def _likelihood_from_score(score: int) -> str:
        if score >= 75:
            return "HIGH"
        if score >= 50:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _clip_score(score: int) -> int:
        return max(0, min(100, int(score)))

    def _deterministic(self, article: Dict) -> ImpactTriageResult:
        title = str(article.get("title", "") or "")
        summary = str(article.get("summary", "") or "")
        category = str(article.get("event_category", "cybersecurity") or "cybersecurity")
        try:
            distress_score = int(article.get("distress_score") or 0)
        except (TypeError, ValueError):
            distress_score = 0
        distress_likelihood = str(article.get("distress_likelihood", "") or "").upper().strip()
        event_subtype = str(article.get("event_subtype", "") or "").strip()

        content = f"{title} {summary}".lower()
        # Layered ownership:
        # - Distress model in main.py remains source-of-truth for category-specific severity.
        # - Impact triage derives from that distress context plus lightweight materiality cues.
        score = 25 + int(distress_score * 0.55)
        reasons: List[str] = []

        if distress_likelihood == "HIGH":
            score += 12
            reasons.append("High distress likelihood supports material impact risk")
        elif distress_likelihood == "MEDIUM":
            score += 6
            reasons.append("Medium distress likelihood supports moderate impact risk")

        if event_subtype:
            score += 4
            reasons.append("Event subtype classification indicates a concrete catalyst shape")

        material_markers = [
            ("chapter 11", 12, "Bankruptcy language usually reprices quickly"),
            ("chapter 7", 12, "Liquidation language usually reprices quickly"),
            ("bankruptcy", 10, "Bankruptcy processes often trigger direct repricing"),
            ("covenant default", 10, "Debt-default language elevates financing risk"),
            ("payment default", 10, "Payment default language elevates financing risk"),
            ("indictment", 10, "Criminal-process language adds governance and legal tail risk"),
            ("sec charges", 10, "SEC charges can drive penalties and prolonged overhang"),
            ("restatement", 10, "Restatements can reset trust in reported fundamentals"),
            ("class i recall", 10, "Class I recall language implies severe product risk"),
            ("grounding", 10, "Grounding actions can halt revenue-generating operations"),
            ("do not use", 8, "Urgent safety directives signal immediate commercial disruption"),
            ("material cybersecurity incident", 10, "Material incident language implies broad fallout"),
            ("ransomware", 8, "Ransomware often carries operational and recovery cost"),
            ("production halt", 8, "Production halts can directly reduce near-term output"),
            ("supplier bankruptcy", 8, "Supplier failures can strand production and deliveries"),
            ("hostile bid", 7, "Hostile bids often increase near-term event volatility"),
            ("deal termination", 9, "Deal breaks can remove embedded transaction premium"),
            ("ceo resigns", 7, "CEO turnover can raise near-term execution uncertainty"),
            ("terminated for cause", 9, "For-cause terminations can signal acute governance risk"),
            ("raised guidance", 8, "Guidance raises can still be high-impact catalysts"),
            ("beat estimates", 6, "Earnings surprises can materially move expectations"),
            ("record revenue", 6, "Record revenue often shifts valuation narrative"),
            ("ofac", 10, "OFAC designations can freeze assets and block transactions"),
            ("entity list", 9, "Entity-list addition severs trade and supply relationships"),
            ("export ban", 9, "Export bans can eliminate revenue channels overnight"),
            ("sanctions violation", 10, "Sanctions-violation language implies penalties and enforcement"),
            ("asset freeze", 9, "Asset freezes directly impair cash availability"),
            ("forced divestiture", 8, "Forced divestitures can destroy embedded value"),
            ("profit warning", 9, "Profit warnings often trigger rapid repricing"),
            ("guidance cut", 8, "Guidance cuts compress forward earnings expectations"),
            ("earnings miss", 7, "Earnings misses can trigger analyst downgrades"),
            ("negative preannouncement", 9, "Negative preannouncements front-run larger misses"),
            ("revenue warning", 8, "Revenue warnings signal fundamental demand weakness"),
            ("hindenburg", 12, "Named activist-short publication commonly drives acute drawdowns"),
            ("muddy waters", 12, "Named activist-short publication commonly drives acute drawdowns"),
            ("activist short", 10, "Activist short framing tends to trigger rapid repricing"),
            ("short-seller report", 10, "Short-seller reports often produce single-day drawdowns"),
            ("short report", 9, "Short-report publication often produces single-day drawdowns"),
            ("fabricated revenue", 11, "Alleged-fabrication language intensifies downside narrative"),
            ("cut to junk", 11, "Junk downgrade forces institutional selling"),
            ("fallen angel", 11, "Fallen-angel status triggers structural selling"),
            ("speculative grade", 8, "Speculative-grade reclassification impacts investor base"),
            ("credit rating downgrade", 8, "Credit downgrades raise refinancing costs"),
            ("substantial doubt", 10, "Substantial-doubt auditor language flags solvency risk"),
            ("auditor resignation", 9, "Auditor resignations often trigger credibility shocks"),
            ("non-reliance on previously issued", 10, "Non-reliance language routinely precedes restatements"),
            ("withdraws guidance", 9, "Guidance withdrawal increases forward uncertainty"),
            ("suspends guidance", 9, "Guidance suspension signals visibility breakdown"),
            ("cuts full-year guidance", 8, "Full-year cuts compress valuation multiples"),
            ("proxy fight", 8, "Proxy fights drive governance-related volatility"),
            ("proxy contest", 8, "Proxy contests drive governance-related volatility"),
            ("schedule 13d", 6, "13D filings disclose activist positioning"),
            ("nationwide strike", 9, "Nationwide strikes materially cut near-term production"),
            ("prolonged strike", 8, "Prolonged stoppages compress near-term earnings"),
            ("work stoppage", 7, "Work stoppages impair near-term output"),
            ("uaw strike", 8, "Auto sector stoppages carry material impact"),
            ("motion to dismiss denied", 8, "Denied dismissals increase litigation exposure"),
            ("class certification", 7, "Class certification amplifies exposure"),
            ("cluster of insider sales", 7, "Insider selling clusters can front-run bad news"),
            ("c-suite selling", 7, "C-suite selling implies informed sell signal"),
            ("cfo sold shares", 7, "CFO share sales carry reporting-context weight"),
        ]

        for marker, weight, reason in material_markers:
            if keyword_in_text(marker, content):
                score += weight
                reasons.append(reason)

        dampeners = [
            ("rumor", 8, "Rumor framing lowers confidence in immediate repricing"),
            ("speculation", 8, "Speculative framing lowers confidence in immediate repricing"),
            ("may", 3, "Tentative wording can reduce near-term impact confidence"),
            ("considering", 3, "Exploratory wording can reduce near-term impact confidence"),
            ("preliminary", 4, "Preliminary disclosures are often revised"),
        ]
        for marker, weight, reason in dampeners:
            if keyword_in_text(marker, content):
                score -= weight
                reasons.append(reason)

        # Materiality enricher: deterministic regex pass; the LLM path is
        # intentionally NOT called here to avoid surprising spend. Callers that
        # want LLM-backed materiality should invoke `materiality_extraction.extract`
        # with a shared LLMClient and merge the result into the article dict
        # before calling `evaluate()`, or set the fields directly.
        pre_materiality = {
            "materiality_usd": article.get("materiality_usd"),
            "materiality_pct_revenue": article.get("materiality_pct_revenue"),
            "materiality_unit_count": article.get("materiality_unit_count"),
        }
        if any(v is not None for v in pre_materiality.values()) or _extract_materiality is None:
            materiality_reasons: List[str] = []
            materiality_bonus = 0
            if any(v is not None for v in pre_materiality.values()):
                class _PreMat:
                    materiality_usd = pre_materiality["materiality_usd"]
                    materiality_pct_revenue = pre_materiality["materiality_pct_revenue"]
                    materiality_unit_count = pre_materiality["materiality_unit_count"]
                materiality_bonus = materiality_impact_bonus(_PreMat())
                if materiality_bonus > 0:
                    materiality_reasons.append(
                        f"Quantified materiality adds +{materiality_bonus} to impact"
                    )
            if materiality_reasons:
                reasons.extend(materiality_reasons)
            score += materiality_bonus
        else:
            mat = _extract_materiality(article)
            bonus = materiality_impact_bonus(mat)
            if bonus > 0:
                score += bonus
                reasons.append(
                    f"Quantified materiality adds +{bonus} to impact"
                )

        score = self._clip_score(score)
        likelihood = self._likelihood_from_score(score)
        topic = event_subtype or category.replace("_", " ").strip()
        headline = " ".join(title.split())
        lead = f"{topic}: {headline}" if headline else topic
        drivers = " / ".join(reasons[:2]) if reasons else "headline/detail severity cues"
        summary_line = (
            f"{lead}. Estimated {likelihood} impact ({score}/100); "
            f"primary drivers: {drivers}."
        )
        return ImpactTriageResult(
            impact_score=score,
            impact_likelihood=likelihood,
            impact_summary=summary_line[:500],
            triage_engine="deterministic",
            reasons=reasons[:4],
        )

    def _http_agent_call(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Live HTTP call that the LLMClient will invoke only when budget allows."""
        if requests is None:  # pragma: no cover
            raise RuntimeError("requests library not available")
        headers = {"Content-Type": "application/json"}
        if self.agent_api_key:
            headers["Authorization"] = f"Bearer {self.agent_api_key}"
        resp = requests.post(
            self.agent_endpoint,
            json=payload,
            headers=headers,
            timeout=self.agent_timeout_seconds,
        )
        resp.raise_for_status()
        data = resp.json() if hasattr(resp, "json") else {}
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else {}
        return {
            "data": data if isinstance(data, dict) else {},
            "input_tokens": int(usage.get("input_tokens", 0) or 0),
            "output_tokens": int(usage.get("output_tokens", 0) or 0),
        }

    def _agent_assisted(self, article: Dict, deterministic: ImpactTriageResult) -> Optional[ImpactTriageResult]:
        if not (self.agent_enabled and self.agent_endpoint and self._llm_client and requests):
            return None

        payload = {
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "event_category": article.get("event_category", ""),
            "distress_score": article.get("distress_score", ""),
            "deterministic": deterministic.as_dict(),
        }

        try:
            distress_score_int = int(article.get("distress_score") or 0)
        except (TypeError, ValueError):
            distress_score_int = 0

        result = self._llm_client.call(
            module="triage",
            prompt_key="impact_triage_v1",
            prompt_payload=payload,
            event_category=str(article.get("event_category", "") or ""),
            distress_score=distress_score_int,
            provider=self.agent_provider or "generic_http",
            model=self.agent_model,
            call_fn=self._http_agent_call,
        )
        if not result.used_llm or not isinstance(result.data, dict):
            return None

        data = result.data
        try:
            score = self._clip_score(int(data.get("impact_score", deterministic.impact_score)))
        except (TypeError, ValueError):
            score = deterministic.impact_score
        likelihood = str(data.get("impact_likelihood", self._likelihood_from_score(score))).upper()
        if likelihood not in ("LOW", "MEDIUM", "HIGH"):
            likelihood = self._likelihood_from_score(score)
        summary = str(data.get("impact_summary", "") or "").strip()
        reasons = data.get("reasons", [])
        if not isinstance(reasons, list):
            reasons = []
        engine = "agent_cached" if result.decision == DECISION_CACHE_HIT else "agent"
        return ImpactTriageResult(
            impact_score=score,
            impact_likelihood=likelihood,
            impact_summary=(summary or deterministic.impact_summary)[:500],
            triage_engine=engine,
            reasons=[str(r) for r in reasons[:4]],
        )

    def evaluate(self, article: Dict) -> Dict:
        """Return impact-triage dict with fallback semantics."""
        deterministic = self._deterministic(article)
        if not self.enabled:
            return deterministic.as_dict()

        assisted = self._agent_assisted(article, deterministic)
        if assisted:
            return assisted.as_dict()
        if self.fallback_to_deterministic:
            return deterministic.as_dict()

        # Explicit fallback disabled: return minimal structure and let caller decide.
        out = deterministic.as_dict()
        out["impact_summary"] = "Impact triage unavailable (agent failed and fallback disabled)."
        out["triage_engine"] = "unavailable"
        return out

