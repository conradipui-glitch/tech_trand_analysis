from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering, DBSCAN
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import (
    adjusted_rand_score,
    completeness_score,
    homogeneity_score,
    normalized_mutual_info_score,
    v_measure_score,
)

from tech_trend_analysis.evaluation import load_benchmark_dataset


THRESHOLDS = [round(value, 3) for value in np.arange(0.05, 0.651, 0.025)]
HYBRID_ALPHAS = (0.80, 0.90, 0.95)


def evaluate(true_labels, predicted_labels, *, algorithm: str, params: dict):
    counts = Counter(int(label) for label in predicted_labels if int(label) >= 0)
    noise_count = sum(1 for label in predicted_labels if int(label) < 0)
    cluster_count = len(counts)
    singleton_count = sum(1 for count in counts.values() if count == 1)
    return {
        "algorithm": algorithm,
        "params": params,
        "ari": adjusted_rand_score(true_labels, predicted_labels),
        "nmi": normalized_mutual_info_score(true_labels, predicted_labels),
        "homogeneity": homogeneity_score(true_labels, predicted_labels),
        "completeness": completeness_score(true_labels, predicted_labels),
        "v_measure": v_measure_score(true_labels, predicted_labels),
        "purity_weighted_v": v_measure_score(true_labels, predicted_labels, beta=0.5),
        "cluster_count": cluster_count,
        "noise_count": noise_count,
        "singleton_count": singleton_count,
    }


def ranking_key(row, true_cluster_count: int):
    # False merges are more damaging than temporary over-segmentation for an
    # emerging-trend detector, so the beta=0.5 V-measure slightly favors
    # homogeneity while still penalizing a forest of singletons.
    return (
        row["purity_weighted_v"],
        row["ari"],
        row["v_measure"],
        -abs(row["cluster_count"] - true_cluster_count),
        -row["noise_count"],
        -row["singleton_count"],
    )


def dense_distance(vectors):
    similarity = np.clip(vectors @ vectors.T, -1.0, 1.0)
    distance = 1.0 - similarity
    np.fill_diagonal(distance, 0.0)
    return distance


def hybrid_distance(vectors, texts, alpha: float):
    tfidf = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),
        sublinear_tf=True,
        norm="l2",
    ).fit_transform(texts)
    lexical_similarity = (tfidf @ tfidf.T).toarray()
    dense_similarity = np.clip(vectors @ vectors.T, -1.0, 1.0)
    similarity = alpha * dense_similarity + (1.0 - alpha) * lexical_similarity
    distance = 1.0 - similarity
    distance = np.clip(distance, 0.0, 2.0)
    np.fill_diagonal(distance, 0.0)
    return distance


def run_algorithm(vectors, texts, algorithm: str, params: dict):
    if algorithm == "agglomerative_average_cosine":
        return AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=float(params["distance_threshold"]),
            compute_full_tree=True,
        ).fit_predict(vectors)
    if algorithm == "agglomerative_hybrid_dense_tfidf":
        distance = hybrid_distance(vectors, texts, float(params["dense_alpha"]))
        return AgglomerativeClustering(
            n_clusters=None,
            metric="precomputed",
            linkage="average",
            distance_threshold=float(params["distance_threshold"]),
            compute_full_tree=True,
        ).fit_predict(distance)
    if algorithm == "dbscan_cosine":
        return DBSCAN(
            eps=float(params["eps"]),
            min_samples=int(params["min_samples"]),
            metric="cosine",
        ).fit_predict(vectors)
    raise ValueError(f"unknown algorithm: {algorithm}")


def sweep(vectors, texts, true_labels):
    results = []
    for threshold in THRESHOLDS:
        params = {"distance_threshold": float(threshold)}
        labels = run_algorithm(vectors, texts, "agglomerative_average_cosine", params)
        results.append(
            evaluate(
                true_labels,
                labels,
                algorithm="agglomerative_average_cosine",
                params=params,
            )
        )

    for alpha in HYBRID_ALPHAS:
        for threshold in THRESHOLDS:
            params = {
                "distance_threshold": float(threshold),
                "dense_alpha": float(alpha),
            }
            labels = run_algorithm(
                vectors,
                texts,
                "agglomerative_hybrid_dense_tfidf",
                params,
            )
            results.append(
                evaluate(
                    true_labels,
                    labels,
                    algorithm="agglomerative_hybrid_dense_tfidf",
                    params=params,
                )
            )

    for eps in THRESHOLDS:
        for min_samples in (2, 3):
            params = {"eps": float(eps), "min_samples": min_samples}
            labels = run_algorithm(vectors, texts, "dbscan_cosine", params)
            results.append(
                evaluate(
                    true_labels,
                    labels,
                    algorithm="dbscan_cosine",
                    params=params,
                )
            )

    true_cluster_count = len(set(int(value) for value in true_labels))
    ranked = sorted(
        results,
        key=lambda row: ranking_key(row, true_cluster_count),
        reverse=True,
    )
    return ranked, results


def cluster_composition(rows, predicted_labels):
    composition = defaultdict(Counter)
    for row, label in zip(rows, predicted_labels, strict=True):
        composition[str(int(label))][row["cluster"]] += 1
    return {
        label: dict(sorted(counts.items()))
        for label, counts in sorted(composition.items(), key=lambda item: int(item[0]))
    }


def benchmark_subset(rows, vectors):
    cluster_names = sorted({row["cluster"] for row in rows})
    cluster_to_id = {name: idx for idx, name in enumerate(cluster_names)}
    true_labels = np.array([cluster_to_id[row["cluster"]] for row in rows])
    texts = [row["text"] for row in rows]
    ranked, results = sweep(vectors, texts, true_labels)
    best = dict(ranked[0])
    best_labels = run_algorithm(vectors, texts, best["algorithm"], best["params"])
    best["composition"] = cluster_composition(rows, best_labels)
    return {
        "document_count": len(rows),
        "true_cluster_count": len(cluster_names),
        "best": best,
        "top10": ranked[:10],
        "all_results": results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--evaluation-dir", default="evaluation")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    dataset = load_benchmark_dataset(args.evaluation_dir)
    rows = dataset.documents
    texts = [row["text"] for row in rows]

    model = SentenceTransformer(args.model, device="cpu")
    started = time.perf_counter()
    vectors = model.encode(
        texts,
        batch_size=args.batch_size,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )
    encode_seconds = time.perf_counter() - started

    global_result = benchmark_subset(rows, vectors)
    by_profile = {}
    for profile in sorted({row["profile"] for row in rows}):
        indices = [index for index, row in enumerate(rows) if row["profile"] == profile]
        profile_rows = [rows[index] for index in indices]
        profile_vectors = vectors[indices]
        by_profile[profile] = benchmark_subset(profile_rows, profile_vectors)

    payload = {
        "model": args.model,
        "embedding_dimension": int(vectors.shape[1]),
        "encode_seconds": encode_seconds,
        "global": global_result,
        "by_profile": by_profile,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "global_best": global_result["best"],
                "profile_best": {
                    profile: result["best"] for profile, result in by_profile.items()
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
