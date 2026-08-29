from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_TOKEN_RE = re.compile(r"(?u)\b[\w-]{2,}\b")
_GENERIC_TERMS = {
    "a", "an", "and", "for", "from", "in", "of", "on", "the", "to", "with",
    "approach", "based", "large", "model", "models", "new", "system", "systems",
    "technology", "technologies", "using",
}


@dataclass(frozen=True, slots=True)
class SampleGateResult:
    raw_count: int
    sample_count: int
    matched_sample_count: int
    estimated_count: int
    sample_precision: float
    accepted_indices: tuple[int, ...]
    similarities: tuple[float, ...]
    anchor_coverages: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_count": self.raw_count,
            "sample_count": self.sample_count,
            "matched_sample_count": self.matched_sample_count,
            "estimated_count": self.estimated_count,
            "sample_precision": round(self.sample_precision, 4),
            "accepted_indices": list(self.accepted_indices),
            "similarities": [round(value, 4) for value in self.similarities],
            "anchor_coverages": [round(value, 4) for value in self.anchor_coverages],
        }


def gate_sampled_count(
    *,
    raw_count: int,
    sample_texts: Sequence[str],
    anchor_text: str,
    aliases: Sequence[str] = (),
    context_terms: Sequence[str] = (),
    min_similarity: float = 0.16,
    min_anchor_coverage: float = 0.34,
    strong_similarity: float = 0.42,
    strong_anchor_coverage: float = 0.67,
) -> SampleGateResult:
    """Estimate cluster-conditioned provider volume from representative samples.

    Provider search counts are retrieval volume, not proof that every result belongs
    to the semantic trend cluster. Production backfill uses vector-to-centroid
    membership. Retrospective validation uses this conservative proxy because it
    cannot materialize every historical result.

    When aliases are configured, a normal acceptance requires a discriminative alias
    plus configured domain context. This is important for ambiguous terms such as
    LoRA/LoRa and generic phrases such as "low rank adaptation". A result without an
    alias may pass only when both semantic similarity and anchor-term coverage are
    exceptionally strong. One sampled match is never amplified to the provider total.
    """
    if raw_count < 0:
        raise ValueError("raw_count must be >= 0")
    for name, value in (
        ("min_similarity", min_similarity),
        ("min_anchor_coverage", min_anchor_coverage),
        ("strong_similarity", strong_similarity),
        ("strong_anchor_coverage", strong_anchor_coverage),
    ):
        if not 0 <= value <= 1:
            raise ValueError(f"{name} must be in [0, 1]")

    texts = [str(value or "").strip() for value in sample_texts]
    if raw_count == 0 or not texts:
        return SampleGateResult(raw_count, len(texts), 0, 0, 0.0, (), (), ())

    anchor = str(anchor_text or "").strip()
    if not anchor:
        raise ValueError("anchor_text must be non-empty")

    corpus = [anchor, *texts]
    try:
        matrix = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b[\w-]{2,}\b",
            sublinear_tf=True,
        ).fit_transform(corpus)
        similarities = cosine_similarity(matrix[1:], matrix[:1]).ravel()
    except ValueError:
        similarities = np.zeros(len(texts), dtype=np.float64)

    anchor_terms = _key_terms(anchor)
    normalized_aliases = tuple(_normalize_phrase(value) for value in aliases if str(value).strip())
    normalized_context = tuple(_normalize_phrase(value) for value in context_terms if str(value).strip())

    accepted: list[int] = []
    coverages: list[float] = []
    for index, (text, raw_similarity) in enumerate(zip(texts, similarities, strict=True)):
        normalized_text = _normalize_phrase(text)
        text_tokens = set(normalized_text.split())
        sample_terms = _key_terms(text)
        coverage = (
            len(anchor_terms.intersection(sample_terms)) / len(anchor_terms)
            if anchor_terms
            else 0.0
        )
        coverages.append(coverage)

        phrase_hit = any(" " in alias and alias in normalized_text for alias in normalized_aliases)
        short_alias_hit = any(" " not in alias and alias in text_tokens for alias in normalized_aliases)
        context_hit = not normalized_context or any(term in normalized_text for term in normalized_context)
        alias_hit = (phrase_hit or short_alias_hit) and context_hit

        ordinary_semantic_hit = (
            float(raw_similarity) >= min_similarity
            and coverage >= min_anchor_coverage
        )
        strong_semantic_hit = (
            float(raw_similarity) >= strong_similarity
            and coverage >= strong_anchor_coverage
        )

        if normalized_aliases:
            accepted_result = alias_hit or strong_semantic_hit
        else:
            accepted_result = ordinary_semantic_hit

        if accepted_result:
            accepted.append(index)

    matched = len(accepted)
    sample_count = len(texts)
    precision = matched / sample_count if sample_count else 0.0

    if matched == 0:
        estimated = 0
    elif raw_count <= sample_count:
        estimated = min(raw_count, matched)
    elif matched == 1:
        estimated = 1
    else:
        estimated = max(matched, int(round(raw_count * precision)))
        estimated = min(raw_count, estimated)

    return SampleGateResult(
        raw_count=raw_count,
        sample_count=sample_count,
        matched_sample_count=matched,
        estimated_count=estimated,
        sample_precision=precision,
        accepted_indices=tuple(accepted),
        similarities=tuple(float(value) for value in similarities),
        anchor_coverages=tuple(coverages),
    )


def _key_terms(text: str) -> set[str]:
    return {
        token.casefold().strip("-")
        for token in _TOKEN_RE.findall(text.casefold())
        if token.casefold().strip("-") not in _GENERIC_TERMS
        and len(token.casefold().strip("-")) >= 3
    }


def _normalize_phrase(value: str) -> str:
    return " ".join(token.casefold().strip("-") for token in _TOKEN_RE.findall(str(value)))
