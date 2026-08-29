from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import time
from pathlib import Path

from tech_trend_analysis.evaluation import load_benchmark_dataset, run_embedding_benchmark


class SentenceTransformerProvider:
    def __init__(self, model_id: str, *, batch_size: int = 16) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_id
        self.model_id = model_id
        self.batch_size = batch_size
        started = time.perf_counter()
        self.model = SentenceTransformer(model_id, device="cpu")
        self.load_seconds = time.perf_counter() - started

    def embed(self, texts, *, mode: str):
        kwargs = {
            "batch_size": self.batch_size,
            "convert_to_numpy": True,
            "normalize_embeddings": True,
            "show_progress_bar": False,
        }
        if mode == "query" and self.model_id == "Qwen/Qwen3-Embedding-0.6B":
            kwargs["prompt_name"] = "query"
        vectors = self.model.encode(list(texts), **kwargs)
        return vectors.tolist()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--evaluation-dir", default="evaluation")
    parser.add_argument("--output", required=True)
    parser.add_argument("--batch-size", type=int, default=16)
    args = parser.parse_args()

    dataset = load_benchmark_dataset(args.evaluation_dir)
    provider = SentenceTransformerProvider(args.model, batch_size=args.batch_size)
    report = run_embedding_benchmark(provider, dataset)

    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    result = report.as_dict()
    result.update(
        {
            "model_id": args.model,
            "device": "cpu",
            "batch_size": args.batch_size,
            "model_load_seconds": provider.load_seconds,
            "peak_rss_mb": peak_rss_kb / 1024.0,
            "float32_bytes_per_vector": report.dimension * 4,
            "python": sys.version.split()[0],
            "platform": platform.platform(),
        }
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
