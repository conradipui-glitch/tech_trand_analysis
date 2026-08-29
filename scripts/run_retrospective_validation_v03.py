#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from scripts.run_retrospective_validation import (
    PublicHistoryClient,
    _aggregate_state,
    _first_active_period,
    _first_sustained_period,
    _lead_months,
    month_windows,
)
from tech_trend_analysis.history_filter import SampleGateResult, gate_sampled_count
from tech_trend_analysis.scoring import EmergingScorer


VALIDATION_VERSION = "0.3.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Retrospective v0.3: stable publication-time history only"
    )
    parser.add_argument("--cases", default="validation/retrospective_cases.yaml")
    parser.add_argument("--output", default="validation/results/retrospective-v0.3.json")
    parser.add_argument("--sample-size", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = config.get("cases") if isinstance(config, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrospective config must contain non-empty cases list")

    # PublicHistoryClient requires a token for its GitHub method, but v0.3 does not
    # call that method. GitHub current repository metadata is deliberately excluded
    # from historical first-seen calibration because name/description are mutable.
    token = os.environ.get("GITHUB_TOKEN", "not-used-in-v03").strip() or "not-used-in-v03"
    client = PublicHistoryClient(github_token=token, sample_size=args.sample_size)
    scorer = EmergingScorer()
    try:
        results = [run_case(case, client=client, scorer=scorer) for case in cases]
    finally:
        client.close()

    payload = {
        "validation_version": VALIDATION_VERSION,
        "case_definition_version": config.get("version"),
        "preregistered_at": config.get("preregistered_at"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "historical_evidence_policy": {
            "openalex": (
                "eligible after conservative semantic sample gating because publication_date is a historical event timestamp"
            ),
            "github_repository_search": (
                "audit/discovery only; excluded from historical scoring until a relevant commit/release/tag timestamp is verified"
            ),
            "reason": (
                "repository created_at is immutable, but current name/description/query match are mutable and can leak future terminology backward"
            ),
        },
        "methodology_warning": (
            "This run calibrates first-seen and research trajectory, not the full evidence lifecycle. "
            "Implementation transition is deferred to B-032, which must use timestamp-verified Git history/release evidence."
        ),
        "cases": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                result["id"]: {
                    "first_raw_activity": result["summary"]["first_raw_activity"],
                    "first_semantic_activity": result["summary"]["first_semantic_activity"],
                    "first_sustained_activity": result["summary"]["first_sustained_activity"],
                    "first_useful_signal": result["summary"]["first_useful_signal"],
                    "lead_months": result["summary"]["lead_months"],
                    "target_met": result["summary"]["target_met"],
                    "pre_origin_raw_count": result["summary"]["pre_origin_raw_count"],
                    "pre_origin_count": result["summary"]["pre_origin_count"],
                }
                for result in results
            },
            ensure_ascii=False,
            indent=2,
        )
    )


def run_case(
    case: dict[str, Any],
    *,
    client: PublicHistoryClient,
    scorer: EmergingScorer,
) -> dict[str, Any]:
    case_id = _required_str(case, "id")
    start = date.fromisoformat(_required_str(case, "validation_start"))
    milestone = date.fromisoformat(_required_str(case["milestone"], "date"))
    origin = date.fromisoformat(_required_str(case["origin"], "date"))
    semantic = case.get("semantic_filter") if isinstance(case.get("semantic_filter"), dict) else {}
    anchor = str(
        semantic.get("anchor")
        or case.get("label")
        or case.get("technology_direction")
        or ""
    ).strip()
    aliases = tuple(str(value) for value in semantic.get("aliases", []) if str(value).strip())
    context_terms = tuple(
        str(value) for value in semantic.get("context_terms", []) if str(value).strip()
    )

    windows = list(month_windows(start, milestone))
    curve: list[dict[str, Any]] = []
    for index, window in enumerate(windows, start=1):
        print(f"[{case_id}] {index}/{len(windows)} {window.key}", flush=True)
        openalex = client.openalex_month(_required_str(case, "openalex_query"), window)
        gate = gate_sampled_count(
            raw_count=int(openalex["count"]),
            sample_texts=[str(item.get("title") or "") for item in openalex["samples"]],
            anchor_text=anchor,
            aliases=aliases,
            context_terms=context_terms,
        )
        openalex["semantic_gate"] = gate.to_dict()
        openalex["accepted_sample_actors"] = _accepted_sample_actors(openalex["samples"], gate)

        research = gate.estimated_count
        curve.append(
            {
                "period": window.key,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "raw_research_count": int(openalex["count"]),
                "raw_implementation_count": 0,
                "raw_total_count": int(openalex["count"]),
                "research_count": research,
                "implementation_count": 0,
                "total_count": research,
                "openalex": openalex,
                "github": {
                    "count": 0,
                    "samples": [],
                    "sample_actors": [],
                    "accepted_sample_actors": [],
                    "historical_eligibility": "excluded_mutable_metadata",
                    "reason": "requires first relevant commit/release/tag verification",
                },
            }
        )

    first_raw = next((row["period"] for row in curve if row["raw_total_count"] > 0), None)
    pre_origin_raw_count = sum(
        row["raw_total_count"]
        for row in curve
        if date.fromisoformat(row["start"]) < origin
    )
    pre_origin_count = sum(
        row["total_count"]
        for row in curve
        if date.fromisoformat(row["start"]) < origin
    )

    timeline: list[dict[str, Any]] = []
    for end_index, row in enumerate(curve):
        prefix = curve[: end_index + 1]
        first_sustained = _first_sustained_period(prefix)
        if first_sustained is None:
            timeline.append(
                {"period": row["period"], "score": None, "reason": "no_sustained_signal_yet"}
            )
            continue
        state = _aggregate_state(case, prefix, first_sustained=first_sustained)
        score = scorer.score(state, as_of=date.fromisoformat(row["end"]))
        timeline.append(
            {
                "period": row["period"],
                "score": round(score.total, 4),
                "confidence": round(score.confidence, 4),
                "stage": score.stage,
                "components": {
                    key: round(component.value, 4)
                    for key, component in score.components.items()
                },
            }
        )

    expectation = case.get("preregistered_expectation") or {}
    min_score = float(expectation.get("useful_signal_score", 60))
    min_confidence = float(expectation.get("useful_signal_confidence", 0.45))
    target_lead = int(expectation.get("target_lead_months", 3))
    first_useful = next(
        (
            row["period"]
            for row in timeline
            if isinstance(row.get("score"), (int, float))
            and row["score"] >= min_score
            and row.get("confidence", 0) >= min_confidence
        ),
        None,
    )
    lead_months = _lead_months(first_useful, milestone) if first_useful else None
    target_met = lead_months is not None and lead_months >= target_lead

    return {
        "id": case_id,
        "label": case.get("label"),
        "profile": case.get("profile"),
        "origin": case.get("origin"),
        "milestone": case.get("milestone"),
        "preregistered_expectation": expectation,
        "queries": {
            "openalex": case.get("openalex_query"),
            "github": case.get("github_query"),
        },
        "semantic_filter": {
            "anchor": anchor,
            "aliases": list(aliases),
            "context_terms": list(context_terms),
        },
        "summary": {
            "first_raw_activity": first_raw,
            "first_semantic_activity": _first_active_period(curve),
            "first_sustained_activity": _first_sustained_period(curve),
            "first_useful_signal": first_useful,
            "lead_months": lead_months,
            "target_met": target_met,
            "pre_origin_raw_count": pre_origin_raw_count,
            "pre_origin_count": pre_origin_count,
        },
        "curve": curve,
        "score_timeline": timeline,
    }


def _accepted_sample_actors(
    samples: list[dict[str, Any]], gate: SampleGateResult
) -> list[str]:
    actors: set[str] = set()
    for index in gate.accepted_indices:
        if index >= len(samples):
            continue
        values = samples[index].get("actor_keys")
        if isinstance(values, list):
            actors.update(str(value) for value in values if str(value).strip())
    return sorted(actors)


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    main()
