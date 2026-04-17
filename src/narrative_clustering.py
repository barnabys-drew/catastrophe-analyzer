"""
Narrative clustering enricher.

Groups duplicate stories that describe the same underlying event across feeds so
that downstream watch creation sees one canonical event per cluster instead of
N inflated duplicates. This is the single biggest false-positive reducer in the
plan because multiple feeds routinely publish the same story within minutes.

Two layers, matching the plan's cascade policy:

1. Deterministic clustering (always on):
   - Normalize titles (lowercase, strip punctuation/stopwords, collapse whitespace).
   - Group within a sliding time window by:
     - same (event_category, primary ticker candidates) AND
     - Jaccard similarity of title shingles >= configurable threshold.
   - Merges source_urls so downstream sees all feed hits.

2. Optional LLM refinement (last resort):
   - Run through `llm_client.LLMClient` so budget caps apply.
   - Only invoked when the deterministic pass is ambiguous (e.g. two borderline
     candidates with similarity near the threshold).
   - When enabled, the callable posts each pair to a configured endpoint; when
     disabled/budget-exhausted/dry-run, the deterministic decision stands.

The module does not write to disk or call the network on its own. Integration
points simply pass a list of articles to `cluster_articles` and consume the
returned cluster objects.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

try:
    from llm_client import LLMClient
except ImportError:  # pragma: no cover - llm_client ships with this repo
    LLMClient = None  # type: ignore[assignment]


_STOPWORDS: Set[str] = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "has",
    "have",
    "in",
    "is",
    "it",
    "its",
    "of",
    "on",
    "or",
    "over",
    "says",
    "that",
    "the",
    "their",
    "this",
    "to",
    "was",
    "were",
    "will",
    "with",
    "new",
    "after",
    "amid",
    "around",
    "following",
}

# Words that appear in nearly every market headline and would otherwise inflate
# Jaccard similarity across unrelated stories.
_MARKET_NOISE: Set[str] = {
    "stock",
    "shares",
    "company",
    "inc",
    "corp",
    "corporation",
    "reports",
    "filing",
    "announces",
    "announced",
}

_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize_title(raw: str) -> str:
    """Lowercase + strip punctuation + drop stopwords + compress whitespace."""
    if not raw:
        return ""
    stripped = _PUNCT_RE.sub(" ", raw.lower())
    tokens = [
        t
        for t in stripped.split()
        if t and t not in _STOPWORDS and t not in _MARKET_NOISE and not t.isdigit()
    ]
    return " ".join(tokens)


def _token_set(text: str) -> Set[str]:
    return {t for t in text.split() if len(t) > 2}


def _jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = a & b
    union = a | b
    if not union:
        return 0.0
    return len(inter) / float(len(union))


def _parse_published(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    # Accept common ISO / RSS forms; fail quiet.
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _article_tickers(article: Dict[str, Any]) -> Set[str]:
    """Collect a coarse ticker set from whatever entity fields an article carries."""
    tickers: Set[str] = set()
    for key in ("ticker", "primary_ticker"):
        value = article.get(key)
        if isinstance(value, str) and value.strip():
            tickers.add(value.strip().upper())
    for key in ("tickers", "candidate_tickers", "entities", "mapped_candidates"):
        value = article.get(key)
        if isinstance(value, (list, tuple)):
            for item in value:
                if isinstance(item, str):
                    candidate = item.strip().upper()
                    if candidate:
                        tickers.add(candidate)
                elif isinstance(item, dict):
                    t = item.get("ticker") or item.get("symbol")
                    if isinstance(t, str) and t.strip():
                        tickers.add(t.strip().upper())
    return tickers


@dataclass
class NarrativeCluster:
    cluster_id: str
    event_category: str
    canonical_index: int
    article_indices: List[int] = field(default_factory=list)
    source_urls: List[str] = field(default_factory=list)
    tickers: Set[str] = field(default_factory=set)
    earliest_published: Optional[datetime] = None
    title_tokens: Set[str] = field(default_factory=set)
    decision: str = "deterministic"  # or "llm_refined"

    def size(self) -> int:
        return len(self.article_indices)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "cluster_id": self.cluster_id,
            "event_category": self.event_category,
            "canonical_index": self.canonical_index,
            "article_indices": list(self.article_indices),
            "source_urls": list(self.source_urls),
            "tickers": sorted(self.tickers),
            "earliest_published": (
                self.earliest_published.isoformat()
                if isinstance(self.earliest_published, datetime)
                else None
            ),
            "size": self.size(),
            "decision": self.decision,
        }


def cluster_articles(
    articles: Sequence[Dict[str, Any]],
    *,
    similarity_threshold: float = 0.55,
    time_window_hours: int = 48,
    llm_refine_band: Tuple[float, float] = (0.40, 0.55),
    llm_client: Optional["LLMClient"] = None,
) -> List[NarrativeCluster]:
    """
    Cluster articles into narrative groups.

    Parameters
    ----------
    articles
        Sequence of article dicts with fields like `title`, `summary`,
        `event_category`, `published`, and entity/ticker fields.
    similarity_threshold
        Jaccard similarity at which two articles are considered the same story
        without LLM assistance.
    time_window_hours
        Cap on how far apart two articles can be and still join the same cluster.
    llm_refine_band
        (low, high) window. When deterministic similarity falls in this band, the
        LLMClient may be consulted. `high` should equal `similarity_threshold`.
    llm_client
        Optional shared LLMClient. When None or budget-denied, the deterministic
        decision stands.

    Returns
    -------
    List[NarrativeCluster]
        One cluster per unique event. Articles that don't merge remain as
        singleton clusters so the caller can iterate uniformly.
    """
    clusters: List[NarrativeCluster] = []
    window = timedelta(hours=max(0, time_window_hours))

    for idx, article in enumerate(articles):
        category = str(article.get("event_category", "") or "")
        title = article.get("title", "") or ""
        norm = _normalize_title(title)
        tokens = _token_set(norm)
        tickers = _article_tickers(article)
        published = _parse_published(article.get("published"))

        best_cluster: Optional[NarrativeCluster] = None
        best_sim: float = 0.0
        for cluster in clusters:
            if cluster.event_category != category:
                continue
            if window.total_seconds() > 0 and published and cluster.earliest_published:
                if abs((published - cluster.earliest_published).total_seconds()) > window.total_seconds():
                    continue
            # Ticker intersection gives a strong prior even on short headlines.
            ticker_overlap = bool(tickers & cluster.tickers)
            sim = _jaccard(tokens, cluster.title_tokens)
            if ticker_overlap:
                sim += 0.15
            if sim > best_sim:
                best_sim = sim
                best_cluster = cluster

        decision: Optional[NarrativeCluster] = None
        refine_band_low, refine_band_high = llm_refine_band

        if best_cluster and best_sim >= similarity_threshold:
            decision = best_cluster
        elif (
            best_cluster
            and llm_client is not None
            and refine_band_low <= best_sim < refine_band_high
        ):
            # Optional LLM refinement, routed through the cost-controlled client.
            candidate_article = articles[best_cluster.canonical_index]
            payload = {
                "title_a": title,
                "title_b": candidate_article.get("title", ""),
                "summary_a": article.get("summary", ""),
                "summary_b": candidate_article.get("summary", ""),
                "event_category": category,
                "jaccard": round(best_sim, 3),
                "tickers_a": sorted(tickers),
                "tickers_b": sorted(best_cluster.tickers),
            }
            try:
                distress_score = int(article.get("distress_score") or 0)
            except (TypeError, ValueError):
                distress_score = 0
            result = llm_client.call(
                module="narrative_clustering",
                prompt_key="same_event_v1",
                prompt_payload=payload,
                event_category=category,
                distress_score=distress_score,
            )
            if result.used_llm and isinstance(result.data, dict):
                if bool(result.data.get("same_event", False)):
                    decision = best_cluster
                    decision.decision = "llm_refined"

        if decision is not None:
            decision.article_indices.append(idx)
            if article.get("link"):
                decision.source_urls.append(str(article["link"]))
            decision.tickers |= tickers
            decision.title_tokens |= tokens
            if published and (decision.earliest_published is None or published < decision.earliest_published):
                decision.earliest_published = published
        else:
            new_cluster = NarrativeCluster(
                cluster_id=f"cluster_{idx}",
                event_category=category,
                canonical_index=idx,
                article_indices=[idx],
                source_urls=[str(article.get("link", ""))] if article.get("link") else [],
                tickers=set(tickers),
                earliest_published=published,
                title_tokens=tokens,
            )
            clusters.append(new_cluster)

    return clusters


def canonical_articles(
    articles: Sequence[Dict[str, Any]],
    clusters: Iterable[NarrativeCluster],
) -> List[Dict[str, Any]]:
    """
    Return the canonical article per cluster, augmented with cluster metadata.
    Callers iterate this list instead of the raw article list to avoid creating
    N watches for the same underlying event.
    """
    out: List[Dict[str, Any]] = []
    for cluster in clusters:
        canonical = dict(articles[cluster.canonical_index])
        canonical["narrative_cluster_id"] = cluster.cluster_id
        canonical["narrative_cluster_size"] = cluster.size()
        canonical["narrative_source_urls"] = list(cluster.source_urls)
        canonical["narrative_cluster_decision"] = cluster.decision
        out.append(canonical)
    return out


__all__ = [
    "NarrativeCluster",
    "cluster_articles",
    "canonical_articles",
]
