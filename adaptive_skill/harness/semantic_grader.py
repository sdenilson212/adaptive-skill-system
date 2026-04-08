"""Semantic similarity helpers for Adaptive Skill System harness graders.

Current default behaviour is stdlib-only so semantic-style matching can be
introduced without adding heavyweight runtime dependencies.  A lazy optional
`sentence-transformers` backend is exposed for higher-fidelity similarity when
that dependency is available.
"""

from __future__ import annotations

import json
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

SUPPORTED_SEMANTIC_METHODS = {"sequence_matcher", "sentence_transformers"}
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def normalize_semantic_text(
    value: Any,
    *,
    case_sensitive: bool = False,
    normalize_whitespace: bool = True,
) -> str:
    """Normalize arbitrary observation/reference content into comparable text."""
    text = _to_text(value)
    if not text:
        return ""

    text = unicodedata.normalize("NFKC", text)
    if normalize_whitespace:
        text = " ".join(text.split())
    if not case_sensitive:
        text = text.casefold()
    return text.strip()


def compute_semantic_similarity(
    actual: Any,
    reference: Any,
    *,
    method: str = "sequence_matcher",
    case_sensitive: bool = False,
    normalize_whitespace: bool = True,
    model_name: str = DEFAULT_SENTENCE_TRANSFORMER_MODEL,
) -> float:
    """Return a normalized 0.0–1.0 similarity score for two values."""
    actual_text = normalize_semantic_text(
        actual,
        case_sensitive=case_sensitive,
        normalize_whitespace=normalize_whitespace,
    )
    reference_text = normalize_semantic_text(
        reference,
        case_sensitive=case_sensitive,
        normalize_whitespace=normalize_whitespace,
    )

    if not actual_text or not reference_text:
        return 0.0

    if method == "sequence_matcher":
        score = SequenceMatcher(None, actual_text, reference_text).ratio()
    elif method == "sentence_transformers":
        score = _compute_sentence_transformer_similarity(
            actual_text,
            reference_text,
            model_name=model_name,
        )
    else:
        raise ValueError(
            f"Unsupported semantic similarity method '{method}'; "
            f"expected one of {sorted(SUPPORTED_SEMANTIC_METHODS)}"
        )

    return round(max(0.0, min(float(score), 1.0)), 4)


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, set):
        return json.dumps(sorted(value), ensure_ascii=False)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "semantic_similarity method 'sentence_transformers' requires the "
            "sentence-transformers package to be installed"
        ) from exc
    return SentenceTransformer(model_name)


def _compute_sentence_transformer_similarity(
    actual_text: str,
    reference_text: str,
    *,
    model_name: str,
) -> float:
    model = _load_sentence_transformer(model_name)
    embeddings = model.encode(
        [actual_text, reference_text],
        normalize_embeddings=True,
    )
    if len(embeddings) != 2:
        raise RuntimeError("SentenceTransformer returned an unexpected embedding shape")

    lhs, rhs = embeddings[0], embeddings[1]
    cosine = sum(float(a) * float(b) for a, b in zip(lhs, rhs))
    return (cosine + 1.0) / 2.0


__all__ = [
    "SUPPORTED_SEMANTIC_METHODS",
    "DEFAULT_SENTENCE_TRANSFORMER_MODEL",
    "normalize_semantic_text",
    "compute_semantic_similarity",
]
