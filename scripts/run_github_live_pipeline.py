#!/usr/bin/env python3
"""Local/VPS B-034 smoke. Requires optional embeddings dependencies and GitHub API access."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import jsonschema

from tech_trend_analysis.github_live_pipeline import run_github_pipeline
from tech_trend_analysis.source_router import SourceRouter
from tech_trend_analysis.sources.github import GitHubAdapter
from tech_trend_analysis.sources.github_history import GitHubHistoryClient


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Live GitHub discovery and timestamp-verified history")
    p.add_argument("--direction", required=True, help="e.g. 'retrieval augmented generation'")
    p.add_argument("--query", default=None, help="GitHub repository search text; defaults to direction")
    p.add_argument("--profile", default=None, help="Optional SourceRouter profile override")
    p.add_argument("--alias", action="append", default=[], help="Reviewed cluster alias; repeatable")
    p.add_argument("--context", action="append", default=[], help="Context for ambiguous short aliases")
    p.add_argument("--distinctive", action="append", default=[], help="Unambiguous implementation term")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--sort", choices=("updated", "stars", "forks"), default="updated")
    p.add_argument("--max-history-per-cluster", type=int, default=3)
    p.add_argument("--model", default="BAAI/bge-m3")
    p.add_argument("--similarity-threshold", type=float, default=0.82)
    p.add_argument("--output-dir", default="validation/results/github-live")
    p.add_argument("--sources", default="config/sources.yaml")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "Embedding runtime missing. Install: pip install -e '.[embeddings]'"
        ) from exc

    # Explicitly use one identical embedding model for discovery and history.
    model = SentenceTransformer(args.model)

    def embed(texts):
        return model.encode(list(texts), normalize_embeddings=True, show_progress_bar=False)

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    router = SourceRouter.from_yaml(args.sources)
    with GitHubAdapter(token=token) as adapter, GitHubHistoryClient(token=token) as history:
        result = run_github_pipeline(
            technology_direction=args.direction,
            query_text=args.query or args.direction,
            router=router,
            adapter=adapter,
            history_client=history,
            embed=embed,
            embedding_model=args.model,
            aliases=args.alias,
            context_terms=args.context,
            distinctive_terms=args.distinctive,
            max_discovery=args.limit,
            repository_sort=args.sort,
            max_history_repositories_per_cluster=args.max_history_per_cluster,
            history_similarity_threshold=args.similarity_threshold,
            profile_override=args.profile,
        )

    validator = jsonschema.Draft202012Validator(
        json.loads(Path("schemas/observation.schema.json").read_text(encoding="utf-8")),
        format_checker=jsonschema.FormatChecker(),
    )
    for observation in result.observations:
        validator.validate(observation)

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "observations.jsonl").write_text(
        "".join(json.dumps(obs, ensure_ascii=False) + "\n" for obs in result.observations),
        encoding="utf-8",
    )
    (out / "trend_states.json").write_text(
        json.dumps(result.trend_states, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out / "history_checks.json").write_text(
        json.dumps(result.history_checks, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    summary = result.summary()
    (out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
