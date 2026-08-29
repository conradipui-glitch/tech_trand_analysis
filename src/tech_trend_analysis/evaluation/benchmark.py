from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Sequence


class EmbeddingProvider(Protocol):
    """Provider contract used by B-015.

    Implementations may call a local model, Workers AI, or another API. Query and
    document modes are separate because some embedding models use task-specific
    prompting.
    """

    name: str

    def embed(self, texts: Sequence[str], *, mode: str) -> list[list[float]]: ...


@dataclass(frozen=True, slots=True)
class BenchmarkDataset:
    documents: list[dict[str, Any]]
    queries: list[dict[str, Any]]
    pairs: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class BenchmarkReport:
    provider: str
    dimension: int
    document_count: int
    query_count: int
    elapsed_seconds: float
    recall_at_1: float
    recall_at_3: float
    recall_at_5: float
    mrr: float
    hard_negative_win_rate: float
    pair_ordering_accuracy: float
    ru_mrr: float
    en_mrr: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "dimension": self.dimension,
            "document_count": self.document_count,
            "query_count": self.query_count,
            "elapsed_seconds": self.elapsed_seconds,
            "recall_at_1": self.recall_at_1,
            "recall_at_3": self.recall_at_3,
            "recall_at_5": self.recall_at_5,
            "mrr": self.mrr,
            "hard_negative_win_rate": self.hard_negative_win_rate,
            "pair_ordering_accuracy": self.pair_ordering_accuracy,
            "ru_mrr": self.ru_mrr,
            "en_mrr": self.en_mrr,
        }


def load_benchmark_dataset(root: str | Path) -> BenchmarkDataset:
    root = Path(root)
    return BenchmarkDataset(
        documents=_load_jsonl(root / "embedding_corpus.jsonl"),
        queries=_load_jsonl(root / "retrieval_queries.jsonl"),
        pairs=_load_jsonl(root / "pair_cases.jsonl"),
    )


def run_embedding_benchmark(
    provider: EmbeddingProvider,
    dataset: BenchmarkDataset,
) -> BenchmarkReport:
    started = time.perf_counter()
    document_texts = [row["text"] for row in dataset.documents]
    query_texts = [row["query"] for row in dataset.queries]

    document_vectors_list = provider.embed(document_texts, mode="document")
    query_vectors_list = provider.embed(query_texts, mode="query")

    if len(document_vectors_list) != len(dataset.documents):
        raise ValueError("provider returned wrong document vector count")
    if len(query_vectors_list) != len(dataset.queries):
        raise ValueError("provider returned wrong query vector count")

    document_vectors = {
        row["id"]: vector
        for row, vector in zip(dataset.documents, document_vectors_list, strict=True)
    }
    query_vectors = {
        row["id"]: vector
        for row, vector in zip(dataset.queries, query_vectors_list, strict=True)
    }

    metrics = evaluate_vectors(dataset, document_vectors, query_vectors)
    elapsed = time.perf_counter() - started
    return BenchmarkReport(
        provider=provider.name,
        dimension=metrics["dimension"],
        document_count=len(dataset.documents),
        query_count=len(dataset.queries),
        elapsed_seconds=elapsed,
        recall_at_1=metrics["recall_at_1"],
        recall_at_3=metrics["recall_at_3"],
        recall_at_5=metrics["recall_at_5"],
        mrr=metrics["mrr"],
        hard_negative_win_rate=metrics["hard_negative_win_rate"],
        pair_ordering_accuracy=metrics["pair_ordering_accuracy"],
        ru_mrr=metrics["ru_mrr"],
        en_mrr=metrics["en_mrr"],
    )


def evaluate_vectors(
    dataset: BenchmarkDataset,
    document_vectors: dict[str, Sequence[float]],
    query_vectors: dict[str, Sequence[float]],
) -> dict[str, Any]:
    dimension = _validate_vectors(dataset, document_vectors, query_vectors)
    doc_ids = [row["id"] for row in dataset.documents]

    recalls: dict[int, list[float]] = {1: [], 3: [], 5: []}
    reciprocal_ranks: list[float] = []
    language_rr: dict[str, list[float]] = {"ru": [], "en": []}
    hard_negative_wins = 0

    for query in dataset.queries:
        query_id = query["id"]
        qv = query_vectors[query_id]
        ranked = sorted(
            (
                (_cosine(qv, document_vectors[doc_id]), doc_id)
                for doc_id in doc_ids
            ),
            reverse=True,
        )
        ranked_ids = [doc_id for _score, doc_id in ranked]
        relevant = set(query["relevant_ids"])

        for k in recalls:
            found = len(relevant.intersection(ranked_ids[:k]))
            recalls[k].append(found / len(relevant))

        first_rank = next(
            (index for index, doc_id in enumerate(ranked_ids, 1) if doc_id in relevant),
            None,
        )
        rr = 0.0 if first_rank is None else 1.0 / first_rank
        reciprocal_ranks.append(rr)
        if query.get("language") in language_rr:
            language_rr[query["language"]].append(rr)

        best_relevant = max(_cosine(qv, document_vectors[doc_id]) for doc_id in relevant)
        hard_negatives = query.get("hard_negative_ids") or []
        if hard_negatives:
            best_hard_negative = max(
                _cosine(qv, document_vectors[doc_id]) for doc_id in hard_negatives
            )
            if best_relevant > best_hard_negative:
                hard_negative_wins += 1

    pair_scores: dict[str, float] = {}
    for pair in dataset.pairs:
        pair_scores[pair["id"]] = _cosine(
            document_vectors[pair["left_id"]],
            document_vectors[pair["right_id"]],
        )

    ordering_total = 0
    ordering_correct = 0
    for pair in dataset.pairs:
        comparison_id = pair.get("expected_more_similar_than")
        if not comparison_id:
            continue
        ordering_total += 1
        if pair_scores[pair["id"]] > pair_scores[comparison_id]:
            ordering_correct += 1

    query_count = len(dataset.queries)
    return {
        "dimension": dimension,
        "recall_at_1": _mean(recalls[1]),
        "recall_at_3": _mean(recalls[3]),
        "recall_at_5": _mean(recalls[5]),
        "mrr": _mean(reciprocal_ranks),
        "hard_negative_win_rate": hard_negative_wins / query_count if query_count else 0.0,
        "pair_ordering_accuracy": (
            ordering_correct / ordering_total if ordering_total else 0.0
        ),
        "ru_mrr": _mean(language_rr["ru"]),
        "en_mrr": _mean(language_rr["en"]),
    }


def _validate_vectors(
    dataset: BenchmarkDataset,
    document_vectors: dict[str, Sequence[float]],
    query_vectors: dict[str, Sequence[float]],
) -> int:
    required_document_ids = {row["id"] for row in dataset.documents}
    required_query_ids = {row["id"] for row in dataset.queries}
    if not required_document_ids.issubset(document_vectors):
        raise ValueError("missing document vectors")
    if not required_query_ids.issubset(query_vectors):
        raise ValueError("missing query vectors")

    vectors = [
        *(document_vectors[doc_id] for doc_id in required_document_ids),
        *(query_vectors[query_id] for query_id in required_query_ids),
    ]
    dimensions = {len(vector) for vector in vectors}
    if len(dimensions) != 1:
        raise ValueError("embedding vectors have inconsistent dimensions")
    dimension = next(iter(dimensions))
    if dimension < 1:
        raise ValueError("embedding dimension must be positive")

    for vector in vectors:
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in vector):
            raise ValueError("embedding vector contains non-finite/non-numeric values")
        if math.sqrt(sum(float(value) ** 2 for value in vector)) == 0:
            raise ValueError("zero embedding vector is not allowed")
    return dimension


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(float(a) * float(b) for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(float(value) ** 2 for value in left))
    right_norm = math.sqrt(sum(float(value) ** 2 for value in right))
    return dot / (left_norm * right_norm)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSONL {path}:{line_number}") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"JSONL row must be object: {path}:{line_number}")
        rows.append(payload)
    return rows
