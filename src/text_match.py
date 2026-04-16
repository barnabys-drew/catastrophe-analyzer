"""
Word-boundary-aware keyword matching for article filtering and scoring.

Short or ambiguous tokens (<=5 chars single-word, or multi-word phrases)
use regex word boundaries to avoid substring false positives like
"may" matching "mayor" or "hack" matching "hackathon".

Longer single-word keywords (>5 chars like "ransomware") keep fast
substring matching since false hits are unlikely.
"""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=2048)
def _boundary_pattern(keyword: str) -> re.Pattern[str]:
    return re.compile(r'\b' + re.escape(keyword) + r'\b')


def keyword_in_text(keyword: str, content: str) -> bool:
    """Return True if keyword appears in content with appropriate matching.

    Multi-word phrases always use word boundaries.
    Single-word tokens <=5 chars use word boundaries (avoids "may"→"mayor").
    Longer single words use fast substring containment.
    """
    if ' ' in keyword or len(keyword) <= 5:
        return bool(_boundary_pattern(keyword).search(content))
    return keyword in content
