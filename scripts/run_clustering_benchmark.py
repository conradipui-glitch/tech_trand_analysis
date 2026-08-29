from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering, DBSCAN
from sklearn.metrics import (
    adjusted_rand_score,
    completeness_score,
    homogeneity_score,
    normalized_mutual_info_score,
    v_measure_score,
)

from tech_trend_analysis.evaluation import load_benchmark_dataset


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
        "cluster_count": cluster_count,
        "noise_count": noise_count,
        "singleton_count": singleton_count,
    }


def ranking_key(row, true_cluster_count: int):
    return (
        row["ari"],
        row["v_measure"],
        -abs(row["cluster_count"] - true_cluster_count),
        -row["noise_count"],
        -row["singleton_count"],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="BAAI/bge-m3")
    parser.add_argument("--evaluation-dir", default="evaluation")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    dataset = load_benchmark_dataset(args.evaluation_dir)
    texts = [row["text"] for row in dataset.documents]
    cluster_names = sorted({row["cluster"] for row in dataset.documents})
    cluster_to_id = {name: idx for idx, name in enumerate(cluster_names)}
    true_labels = np.array([cluster_to_id[row["cluster"]] for row in dataset.documents])

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

    results = []
    thresholds = [round(value, 3) for value in np.arange(0.05, 0.651, 0.025)]
    for threshold in thresholds:
        labels = AgglomerativeClustering(
            n_clusters=None,
            metric="cosine",
            linkage="average",
            distance_threshold=float(threshold),
            compute_full_tree=True,
        ).fit_predict(vectors)
        results.append(
            evaluate(
                true_labels,
                labels,
                algorithm="agglomerative_average_cosine",
                params={"distance_threshold": float(threshold)},
            )
        )

    for eps in thresholds:
        for min_samples in (2, 3):
            labels = DBSCAN(
                eps=float(eps),
                min_samples=min_samples,
                metric="cosine",
            ).fit_predict(vectors)
            results.append(
                evaluate(
                    true_labels,
                    labels,
                    algorithm="dbscan_cosine",
                    params={"eps": float(eps), "min_samples": min_samples},
                )
            )

    true_cluster_count = len(cluster_names)
    ranked = sorted(
        results,
        key=lambda row: ranking_key(row, true_cluster_count),
        reverse=True,
    )
    payload = {
        "model": args.model,
        "document_count": len(dataset.documents),
        "true_cluster_count": true_cluster_count,
        "embedding_dimension": int(vectors.shape[1]),
        "encode_seconds": encode_seconds,
        "best": ranked[0],
        "top10": ranked[:10],
        "all_results": results,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"best": payload["best"], "top10": payload["top10"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
