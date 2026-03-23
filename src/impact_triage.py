"""
Impact triage module.

Computes event impact likelihood using:
1) deterministic scoring (always available)
2) optional agent/LLM HTTP provider with deterministic fallback
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

try:
    import requests
except ImportError:  # pragma: no cover - requests exists in project deps
    requests = None


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

    def __init__(self, config: Optional[Dict] = None):
        cfg = config or {}
        triage_cfg = cfg.get("triage", {})
        self.enabled = bool(triage_cfg.get("enabled", True))
        self.agent_enabled = bool(triage_cfg.get("agent_enabled", False))
        self.fallback_to_deterministic = bool(triage_cfg.get("fallback_to_deterministic", True))
        self.agent_timeout_seconds = int(triage_cfg.get("agent_timeout_seconds", 8))
        self.agent_endpoint = (triage_cfg.get("agent_endpoint") or "").strip()
        self.agent_api_key = (triage_cfg.get("agent_api_key") or "").strip()

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
        distress_score = int(article.get("distress_score") or 0)

        content = f"{title} {summary}".lower()
        score = 20 + int(distress_score * 0.35)
        reasons: List[str] = []

        common = [
            ("investigation", 8, "Investigation language implies possible prolonged overhang"),
            ("class action", 8, "Class-action risk adds legal cost uncertainty"),
            ("guidance", 7, "Guidance references can signal earnings impact"),
            ("production halt", 10, "Production halt can directly pressure revenue"),
        ]
        for marker, weight, reason in common:
            if marker in content:
                score += weight
                reasons.append(reason)

        if category == "cybersecurity":
            cyber = [
                ("material cybersecurity incident", 18, "Material incident wording is high-impact"),
                ("ransomware", 14, "Ransomware often has operational and financial fallout"),
                ("service outage", 10, "Outages create immediate service and reputation risk"),
                ("operations disrupted", 12, "Disruption language points to near-term financial pressure"),
                ("regulator", 8, "Regulatory scrutiny can add compliance and penalty risk"),
            ]
            for marker, weight, reason in cyber:
                if marker in content:
                    score += weight
                    reasons.append(reason)
        elif category == "clinical_regulatory_binary":
            clinical = [
                ("complete response letter", 20, "CRL usually delays commercialization"),
                ("clinical hold", 18, "Clinical hold can freeze trial progression"),
                ("trial hold", 18, "Trial hold can freeze trial progression"),
                ("missed primary endpoint", 20, "Missed endpoint can reset program value"),
                ("fda approval", -12, "Approval is de-risking vs distress scenarios"),
                ("met primary endpoint", -10, "Positive efficacy reduces downside pressure"),
            ]
            for marker, weight, reason in clinical:
                if marker in content:
                    score += weight
                    reasons.append(reason)
        elif category == "product_safety_recall":
            safety = [
                ("recall", 16, "Recall language often implies direct cost and brand pressure"),
                ("grounding", 20, "Grounding can materially reduce operating throughput"),
                ("warning letter", 12, "Warning letters can lead to costly remediation"),
                ("contamination", 16, "Contamination events can widen scope and legal exposure"),
                ("injury", 10, "Injury-related language increases litigation risk"),
            ]
            for marker, weight, reason in safety:
                if marker in content:
                    score += weight
                    reasons.append(reason)

        score = self._clip_score(score)
        likelihood = self._likelihood_from_score(score)
        summary_line = (
            f"{category}: {likelihood} impact ({score}/100) based on distress + "
            f"{' / '.join(reasons[:2]) if reasons else 'headline severity cues'}."
        )
        return ImpactTriageResult(
            impact_score=score,
            impact_likelihood=likelihood,
            impact_summary=summary_line[:500],
            triage_engine="deterministic",
            reasons=reasons[:4],
        )

    def _agent_assisted(self, article: Dict, deterministic: ImpactTriageResult) -> Optional[ImpactTriageResult]:
        if not (self.agent_enabled and self.agent_endpoint and requests):
            return None

        payload = {
            "title": article.get("title", ""),
            "summary": article.get("summary", ""),
            "event_category": article.get("event_category", ""),
            "distress_score": article.get("distress_score", ""),
            "deterministic": deterministic.as_dict(),
        }
        headers = {"Content-Type": "application/json"}
        if self.agent_api_key:
            headers["Authorization"] = f"Bearer {self.agent_api_key}"

        try:
            resp = requests.post(
                self.agent_endpoint,
                json=payload,
                headers=headers,
                timeout=self.agent_timeout_seconds,
            )
            resp.raise_for_status()
            data = resp.json() if hasattr(resp, "json") else {}
            score = self._clip_score(int(data.get("impact_score", deterministic.impact_score)))
            likelihood = str(data.get("impact_likelihood", self._likelihood_from_score(score))).upper()
            if likelihood not in ("LOW", "MEDIUM", "HIGH"):
                likelihood = self._likelihood_from_score(score)
            summary = str(data.get("impact_summary", "") or "").strip()
            reasons = data.get("reasons", [])
            if not isinstance(reasons, list):
                reasons = []
            return ImpactTriageResult(
                impact_score=score,
                impact_likelihood=likelihood,
                impact_summary=(summary or deterministic.impact_summary)[:500],
                triage_engine="agent",
                reasons=[str(r) for r in reasons[:4]],
            )
        except Exception:
            return None

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

