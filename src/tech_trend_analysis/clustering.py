from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer


@dataclass(frozen=True, slots=True)
class MicroclusterConfig:
    algorithm: str
    distance_threshold: float
    dense_alpha: float | None = None
    calibration: str = "unvalidated"

    def __post_init__(self) -> None:
        if self.algorithm not in {
            "agglomerative_average_cosine",
            "agglomerative_hybrid_dense_tfidf",
        }:
            raise ValueError(f"unsupported clustering algorithm: {self.algorithm}")
        if not 0 < self.distance_threshold <= 2:
            raise ValueError("distance_threshold must be in (0, 2]")
        if self.algorithm == "agglomerative_hybrid_dense_tfidf":
            if self.dense_alpha is None or not 0 <= self.dense_alpha <= 1:
                raise ValueError("hybrid clustering requires dense_alpha in [0, 1]")


PROFILE_CONFIGS: dict[str, MicroclusterConfig] = {
    "software_ai": MicroclusterConfig(
        algorithm="agglomerative_hybrid_dense_tfidf",
        distance_threshold=0.45,
        dense_alpha=0.90,
        calibration="gold_v0_2026-08-29",
    ),
    "hardware_semiconductor": MicroclusterConfig(
        algorithm="agglomerative_average_cosine",
        distance_threshold=0.40,
        calibration="gold_v0_2026-08-29",
    ),
    # Materials are intentionally conservative. On the v0 corpus, higher
    # thresholds started merging sodium-ion and silicon-anode evidence. A split
    # microcluster can be consolidated later by TrendState; a false merge can
    # corrupt first_seen/growth for two distinct technologies.
    "materials_energy": MicroclusterConfig(
        algorithm="agglomerative_average_cosine",
        distance_threshold=0.30,
        calibration="gold_v0_purity_first_2026-08-29",
    ),
    "bio_medtech": MicroclusterConfig(
        algorithm="agglomerative_hybrid_dense_tfidf",
        distance_threshold=0.35,
        dense_alpha=0.90,
        calibration="fallback_unvalidated",
    ),
    "mixed": MicroclusterConfig(
        algorithm="agglomerative_hybrid_dense_tfidf",
        distance_threshold=0.35,
        dense_alpha=0.90,
        calibration="fallback_unvalidated",
    ),
}


@dataclass(frozen=True, slots=True)
class Microcluster:
    cluster_id: str
    member_ids: tuple[str, ...]
    centroid: tuple[float, ...]
    member_count: int


@dataclass(frozen=True, slots=True)
class MicroclusteringResult:
    profile: str
    config: MicroclusterConfig
    embedding_model: str
    clusters: tuple[Microcluster, ...]
    assignments: dict[str, str]


class Microclusterer:
    """Batch discovery clustering with no pre-specified number of clusters.

    This component creates conservative semantic microclusters from a recent
    observation batch. Long-lived identity, temporal merging and centroid update
    belong to TrendState, not this class.
    """

    def __init__(
        self,
        *,
        embedding_model: str = "BAAI/bge-m3",
        profile_configs: dict[str, MicroclusterConfig] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self.profile_configs = dict(profile_configs or PROFILE_CONFIGS)

    def cluster(
        self,
        *,
        profile: str,
        observation_ids: Sequence[str],
        texts: Sequence[str],
        vectors: Sequence[Sequence[float]],
        config: MicroclusterConfig | None = None,
    ) -> MicroclusteringResult:
        resolved = config or self.profile_configs.get(profile)
        if resolved is None:
            raise ValueError(f"no clustering config for profile: {profile}")

        ids = [str(value).strip() for value in observation_ids]
        docs = [str(value).strip() for value in texts]
        matrix = np.asarray(vectors, dtype=np.float32)
        _validate_inputs(ids, docs, matrix)

        if len(ids) == 1:
            labels = np.array([0], dtype=int)
        elif resolved.algorithm == "agglomerative_average_cosine":
            labels = AgglomerativeClustering(
                n_clusters=None,
                metric="cosine",
                linkage="average",
                distance_threshold=resolved.distance_threshold,
                compute_full_tree=True,
            ).fit_predict(matrix)
        else:
            distance = _hybrid_distance(matrix, docs, resolved.dense_alpha or 0.0)
            labels = AgglomerativeClustering(
                n_clusters=None,
                metric="precomputed",
                linkage="average",
                distance_threshold=resolved.distance_threshold,
                compute_full_tree=True,
            ).fit_predict(distance)

        clusters: list[Microcluster] = []
        assignments: dict[str, str] = {}
        for raw_label in sorted(set(int(label) for label in labels)):
            indices = [index for index, label in enumerate(labels) if int(label) == raw_label]
            members = tuple(sorted(ids[index] for index in indices))
            cluster_id = _stable_cluster_id(profile, members)
            centroid_array = _normalized_centroid(matrix[indices])
            cluster = Microcluster(
                cluster_id=cluster_id,
                member_ids=members,
                centroid=tuple(float(value) for value in centroid_array),
                member_count=len(members),
            )
            clusters.append(cluster)
            for member_id in members:
                assignments[member_id] = cluster_id

        clusters.sort(key=lambda item: item.cluster_id)
        return MicroclusteringResult(
            profile=profile,
            config=resolved,
            embedding_model=self.embedding_model,
            clusters=tuple(clusters),
            assignments=assignments,
        )


def _validate_inputs(ids: list[str], texts: list[str], matrix: np.ndarray) -> None:
    if not ids:
        raise ValueError("microclustering requires at least one observation")
    if len(set(ids)) != len(ids):
        raise ValueError("observation_ids must be unique")
    if any(not value for value in ids):
        raise ValueError("observation_ids must be non-empty")
    if len(texts) != len(ids):
        raise ValueError("texts and observation_ids must have equal length")
    if any(not value for value in texts):
        raise ValueError("texts must be non-empty")
    if matrix.ndim != 2 or matrix.shape[0] != len(ids) or matrix.shape[1] < 1:
        raise ValueError("vectors must be a non-empty 2D matrix matching observations")
    if not np.isfinite(matrix).all():
        raise ValueError("vectors contain non-finite values")
    norms = np.linalg.norm(matrix, axis=1)
    if np.any(norms == 0):
        raise ValueError("zero vectors are not allowed")
    # Agglomerative cosine expects non-zero vectors; normalize here so the same
    # centroids can later be compared by dot product/cosine in TrendState.
    matrix /= norms[:, None]


def _hybrid_distance(matrix: np.ndarray, texts: Sequence[str], dense_alpha: float) -> np.ndarray:
    tfidf = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        norm="l2",
    ).fit_transform(texts)
    lexical_similarity = (tfidf @ tfidf.T).toarray()
    dense_similarity = np.clip(matrix @ matrix.T, -1.0, 1.0)
    similarity = dense_alpha * dense_similarity + (1.0 - dense_alpha) * lexical_similarity
    distance = np.clip(1.0 - similarity, 0.0, 2.0)
    np.fill_diagonal(distance, 0.0)
    return distance


def _normalized_centroid(matrix: np.ndarray) -> np.ndarray:
    centroid = matrix.mean(axis=0)
    norm = float(np.linalg.norm(centroid))
    if norm == 0:
        raise ValueError("cluster centroid is zero")
    return centroid / norm


def _stable_cluster_id(profile: str, members: tuple[str, ...]) -> str:
    payload = profile + "\n" + "\n".join(members)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
    return f"micro:{profile}:{digest}"
