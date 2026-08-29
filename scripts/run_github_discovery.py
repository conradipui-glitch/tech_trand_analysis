#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from tech_trend_analysis.source_router import SourceRouter
from tech_trend_analysis.sources.github import GitHubAdapter, GitHubQuery


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect present-day GitHub implementation observations")
    parser.add_argument("--direction", required=True)
    parser.add_argument("--query", default=None, help="GitHub repository search query; defaults to direction")
    parser.add_argument("--profile", default=None)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--per-page", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--output", required=True)
    parser.add_argument("--sources", default="config/sources.yaml")
    parser.add_argument("--schema", default="schemas/observation.schema.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.limit < 1:
        raise ValueError("limit must be >= 1")

    router = SourceRouter.from_yaml(args.sources)
    route = router.route(args.direction, profile_override=args.profile)
    github_route = next(
        (provider for provider in route.providers if provider.provider == "github"),
        None,
    )
    if github_route is None or not github_route.enabled:
        raise SystemExit(f"GitHub is disabled for source profile {route.profile}")

    observed_at = datetime.now(timezone.utc).replace(microsecond=0)
    query_text = (args.query or args.direction).strip()
    query_id = f"github:{route.profile}:{observed_at.strftime('%Y%m%dT%H%M%SZ')}"
    query = GitHubQuery(
        technology_direction=args.direction,
        source_profile=route.profile,
        query_text=query_text,
        query_id=query_id,
        per_page=args.per_page,
        max_pages=args.max_pages,
    )

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    with GitHubAdapter(token=token) as adapter:
        observations = adapter.collect(query, observed_at=observed_at)[: args.limit]

    schema = json.loads(Path(args.schema).read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    for observation in observations:
        validator.validate(observation)
        if observation.get("published_at") is not None:
            raise AssertionError("GitHub discovery observation must not use mutable repository metadata as historical time")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(observation, ensure_ascii=False, separators=(",", ":")) + "\n")

    print(
        json.dumps(
            {
                "technology_direction": args.direction,
                "profile": route.profile,
                "router_confidence": route.confidence,
                "query": query_text,
                "observation_count": len(observations),
                "output": str(output),
                "time_semantics": "current_snapshot_only",
                "historical_verification_required": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
