"""
Shared retrieval helpers for Adaptive Skill System.

These utilities keep Layer 1 and Layer 2 on the same query-normalization
and keyword extraction logic, so recall / ranking evolves in one place.
"""

from __future__ import annotations

from typing import Iterable, List
from dataclasses import dataclass
import re


_ZH_STOP_PHRASES = {
    "怎么", "如何", "为什么", "什么", "请问", "帮我", "一下", "一种", "这个", "那个",
}
_ZH_STOP_CHARS = {
    "的", "了", "是", "在", "和", "与", "或", "也", "都", "很", "一", "个", "这", "那",
    "有", "到", "对", "为", "以", "及", "请", "把", "给", "做", "用", "呢", "吗",
}
_EN_STOP_WORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "how", "what", "why",
    "when", "where", "your", "you", "are", "can", "use", "need", "make", "build", "create",
}
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_EN_WORD_RE = re.compile(r"[a-z0-9]+")
_NON_TEXT_RE = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class QueryVariant:
    """A rewritten retrieval query used for multi-recall and fusion."""

    query: str
    weight: float
    source: str


def normalize_text(text: str) -> str:
    """Lower-case and collapse punctuation / whitespace for retrieval use."""
    lowered = str(text or "").lower().replace("_", " ")
    lowered = _NON_TEXT_RE.sub(" ", lowered)
    return _SPACE_RE.sub(" ", lowered).strip()



def extract_query_terms(text: str, max_terms: int = 12) -> List[str]:
    """
    Extract stable retrieval terms shared by Layer 1 and Layer 2.

    Strategy:
    - English: keep informative tokens and adjacent two-word phrases.
    - Chinese: remove common prompt filler, then emit whole phrases plus 2/3-grams.
    - Results are de-duplicated and sorted by specificity first.
    """
    normalized = normalize_text(text)
    if not normalized:
        return []

    terms: List[str] = []

    english_words = [
        word for word in _EN_WORD_RE.findall(normalized)
        if len(word) > 2 and word not in _EN_STOP_WORDS
    ]
    terms.extend(english_words)
    for idx in range(len(english_words) - 1):
        left = english_words[idx]
        right = english_words[idx + 1]
        if left in _EN_STOP_WORDS or right in _EN_STOP_WORDS:
            continue
        terms.append(f"{left} {right}")

    zh_source = normalized
    for phrase in _ZH_STOP_PHRASES:
        zh_source = zh_source.replace(phrase, " ")
    for char in _ZH_STOP_CHARS:
        zh_source = zh_source.replace(char, " ")
    zh_source = _SPACE_RE.sub(" ", zh_source)

    for segment in re.findall(r"[\u4e00-\u9fff]{2,}", zh_source):
        if len(segment) >= 2:
            terms.append(segment)
        for n in (2, 3, 4):
            if len(segment) < n:
                continue
            for idx in range(len(segment) - n + 1):
                gram = segment[idx : idx + n]
                if gram not in _ZH_STOP_PHRASES:
                    terms.append(gram)

    unique_terms = _dedupe_preserve_order(terms)
    unique_terms.sort(key=lambda term: (-_term_weight(term), term))
    return unique_terms[:max_terms]



def build_query_variants(text: str, max_terms: int = 8, max_variants: int = 6) -> List[QueryVariant]:
    """Build rewritten query variants for multi-recall and query fusion."""
    raw_text = str(text or "").strip()
    normalized = normalize_text(raw_text)
    if not normalized:
        return []

    keywords = extract_query_terms(raw_text, max_terms=max_terms)
    variants: List[QueryVariant] = []

    if raw_text:
        variants.append(QueryVariant(query=raw_text, weight=1.0, source="full_query"))

    if normalized and normalized != raw_text:
        variants.append(QueryVariant(query=normalized, weight=0.96, source="normalized"))

    semantic_core = " ".join(keywords[: min(3, len(keywords))]).strip()
    if semantic_core and normalize_text(semantic_core) not in {normalized, ""}:
        variants.append(QueryVariant(query=semantic_core, weight=0.88, source="semantic_core"))

    for idx, term in enumerate(keywords):
        weight = max(0.48, 0.82 - idx * 0.06)
        variants.append(QueryVariant(query=term, weight=weight, source="keyword"))

    return _dedupe_query_variants(variants)[:max_variants]



def expand_query_terms(text: str, max_terms: int = 16) -> List[str]:
    """Expand retrieval terms with semantic-core rewrites while keeping determinism."""
    expanded_terms: List[str] = []
    expanded_terms.extend(extract_query_terms(text, max_terms=max_terms))

    for variant in build_query_variants(text, max_terms=min(max_terms, 8), max_variants=6):
        variant_normalized = normalize_text(variant.query)
        if variant.source in {"normalized", "semantic_core"} and _is_informative_variant(variant_normalized):
            expanded_terms.append(variant_normalized)
        if variant.source != "keyword":
            expanded_terms.extend(extract_query_terms(variant.query, max_terms=4))

    unique_terms = _dedupe_preserve_order(expanded_terms)
    unique_terms.sort(key=lambda term: (-_term_weight(term), term))
    return unique_terms[:max_terms]



def weighted_term_coverage(text: str, terms: Iterable[str]) -> float:
    """Return weighted keyword coverage ratio in [0, 1]."""
    normalized = normalize_text(text)
    term_list = [term for term in terms if term]
    if not normalized or not term_list:
        return 0.0

    matched_weight = 0.0
    total_weight = 0.0
    for term in term_list:
        weight = _term_weight(term)
        total_weight += weight
        if term in normalized:
            matched_weight += weight

    if total_weight <= 0:
        return 0.0
    return matched_weight / total_weight



def _dedupe_preserve_order(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for item in items:
        cleaned = item.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return output



def _dedupe_query_variants(items: Iterable[QueryVariant]) -> List[QueryVariant]:
    seen = set()
    output: List[QueryVariant] = []
    for item in items:
        cleaned = item.query.strip()
        normalized = normalize_text(cleaned)
        if not cleaned or not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(QueryVariant(query=cleaned, weight=item.weight, source=item.source))
    return output



def _is_informative_variant(term: str) -> bool:
    if not term:
        return False
    if " " in term:
        return 2 <= len(term.split()) <= 6
    return len(term) >= 4



def _term_weight(term: str) -> float:
    if " " in term:
        return min(4.0, 1.4 + 0.8 * len(term.split()))
    if _CJK_RE.search(term):
        return min(4.0, max(1.0, len(term) - 0.2))
    return min(3.5, max(1.0, len(term) / 3.0))

