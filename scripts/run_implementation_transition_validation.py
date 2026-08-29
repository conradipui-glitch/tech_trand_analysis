#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from tech_trend_analysis.sources.github_history import GitHubHistoryClient, GitHubHistoryQuery


VALIDATION_VERSION = "0.1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate research -> implementation transitions with stable GitHub event timestamps"
    )
    parser.add_argument("--cases", default="validation/retrospective_cases.yaml")
    parser.add_argument("--output", default="validation/results/implementation-transition-v0.1.json")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = config.get("cases") if isinstance(config, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrospective config must contain non-empty cases list")

    token = os.environ.get("GITHUB_TOKEN", "").strip() or None
    with GitHubHistoryClient(token=token) as client:
        results = [run_case(case, client=client) for case in cases]

    payload = {
        "validation_version": VALIDATION_VERSION,
        "case_definition_version": config.get("version"),
        "preregistered_at": config.get("preregistered_at"),
        "generated_at": _iso_z(datetime.now(timezone.utc)),
        "historical_timestamp_policy": {
            "eligible": ["relevant_commit", "relevant_release", "relevant_tag"],
            "ineligible": ["repository_created_at", "current_repository_description"],
            "reason": (
                "repository metadata is mutable and can leak future terminology backward; "
                "Git event timestamps are stable historical events"
            ),
        },
        "cases": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        result["id"]: {
            "status": result["status"],
            "first_implementation": result["summary"]["first_implementation"],
            "research_to_implementation_days": result["summary"]["research_to_implementation_days"],
            "implementation_lead_days_to_milestone": result["summary"]["implementation_lead_days_to_milestone"],
        }
        for result in results
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))

    failures = [result["id"] for result in results if result["status"] != "transition_validated"]
    if failures:
        raise SystemExit(f"implementation transition validation failed: {', '.join(failures)}")


def run_case(case: dict[str, Any], *, client: GitHubHistoryClient) -> dict[str, Any]:
    case_id = _required_str(case, "id")
    profile = _required_str(case, "profile")
    direction = _required_str(case, "technology_direction")
    origin = date.fromisoformat(_required_str(case["origin"], "date"))
    milestone = date.fromisoformat(_required_str(case["milestone"], "date"))

    semantic = case.get("semantic_filter")
    if not isinstance(semantic, dict):
        raise ValueError(f"{case_id}: semantic_filter is required")
    aliases = tuple(str(value) for value in semantic.get("aliases", []) if str(value).strip())
    context_terms = tuple(str(value) for value in semantic.get("context_terms", []) if str(value).strip())

    validation = case.get("implementation_validation")
    repositories = validation.get("repositories") if isinstance(validation, dict) else None
    if not isinstance(repositories, list) or not repositories:
        raise ValueError(f"{case_id}: implementation_validation.repositories is required")

    events: list[dict[str, Any]] = []
    observations: list[dict[str, Any]] = []
    for repo_config in repositories:
        if not isinstance(repo_config, dict):
            continue
        repository = _required_str(repo_config, "repository")
        distinctive_terms = tuple(
            str(value) for value in repo_config.get("distinctive_terms", []) if str(value).strip()
        )
        query = GitHubHistoryQuery(
            repository=repository,
            technology_direction=direction,
            source_profile=profile,
            aliases=aliases,
            context_terms=context_terms,
            distinctive_terms=distinctive_terms,
            query_id=f"validation:{case_id}:{repository}",
        )
        event = client.verify_earliest(query)
        if event is None:
            events.append(
                {
                    "repository": repository,
                    "status": "no_verified_event",
                    "event": None,
                }
            )
            continue
        observation = event.to_observation(query)
        events.append(
            {
                "repository": repository,
                "status": "verified",
                "event": {
                    "kind": event.event_kind,
                    "external_id": event.external_id,
                    "occurred_at": event.occurred_at,
                    "title": event.title,
                    "url": event.url,
                    "matched_terms": list(event.matched_terms),
                },
            }
        )
        observations.append(observation)

    verified = [item for item in events if isinstance(item.get("event"), dict)]
    verified.sort(key=lambda item: _parse_time(item["event"]["occurred_at"]))
    first = verified[0]["event"] if verified else None

    if first is None:
        status = "no_verified_implementation"
        first_date = None
        transition_days = None
        milestone_lead = None
    else:
        first_date = _parse_time(first["occurred_at"]).date()
        transition_days = (first_date - origin).days
        milestone_lead = (milestone - first_date).days
        if first_date < origin:
            status = "suspicious_pre_origin_implementation"
        elif first_date <= milestone:
            status = "transition_validated"
        else:
            status = "implementation_after_milestone"

    return {
        "id": case_id,
        "label": case.get("label"),
        "profile": profile,
        "origin": case.get("origin"),
        "milestone": case.get("milestone"),
        "status": status,
        "summary": {
            "research_origin": origin.isoformat(),
            "first_implementation": first["occurred_at"] if first else None,
            "research_to_implementation_days": transition_days,
            "implementation_lead_days_to_milestone": milestone_lead,
            "verified_repository_count": len(verified),
            "configured_repository_count": len(repositories),
        },
        "repositories": events,
        "observations": observations,
    }


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    main()
