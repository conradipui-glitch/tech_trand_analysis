#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

from tech_trend_analysis.history_filter import SampleGateResult, gate_sampled_count
from tech_trend_analysis.scoring import EmergingScorer
from tech_trend_analysis.trend_state import PeriodBucket, TrendState


OPENALEX_URL = "https://api.openalex.org/works"
VALIDATION_VERSION = "0.4.0"


@dataclass(frozen=True, slots=True)
class MonthWindow:
    key: str
    start: date
    end: date


class OpenAlexHistoryClient:
    def __init__(self, *, sample_size: int = 20) -> None:
        self.sample_size = sample_size
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "tech-trend-analysis-retrospective/0.4"},
        )

    def close(self) -> None:
        self.client.close()

    def month(self, query: str, window: MonthWindow) -> dict[str, Any]:
        payload = self._get_json(
            params={
                "search": query,
                "filter": (
                    f"from_publication_date:{window.start.isoformat()},"
                    f"to_publication_date:{window.end.isoformat()}"
                ),
                "per-page": self.sample_size,
            }
        )
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        samples: list[dict[str, Any]] = []
        actors: set[str] = set()
        for work in results:
            if not isinstance(work, dict):
                continue
            work_actors: set[str] = set()
            for authorship in work.get("authorships") or []:
                if not isinstance(authorship, dict):
                    continue
                for institution in authorship.get("institutions") or []:
                    if isinstance(institution, dict):
                        actor = institution.get("id") or institution.get("display_name")
                        if actor:
                            work_actors.add(f"openalex:institution:{actor}")
                author = authorship.get("author")
                if isinstance(author, dict):
                    actor = author.get("id") or author.get("display_name")
                    if actor:
                        work_actors.add(f"openalex:author:{actor}")
            actors.update(work_actors)
            samples.append(
                {
                    "id": work.get("id"),
                    "title": work.get("title") or work.get("display_name"),
                    "date": work.get("publication_date"),
                    "relevance_score": work.get("relevance_score"),
                    "actor_keys": sorted(work_actors),
                }
            )
        return {
            "count": int(meta.get("count") or 0),
            "sample_actors": sorted(actors),
            "samples": samples,
            "query": query,
        }

    def _get_json(self, *, params: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = self.client.get(OPENALEX_URL, params=params)
                if response.status_code in {429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    delay = (
                        float(retry_after)
                        if retry_after and retry_after.isdigit()
                        else min(2**attempt, 16)
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("OpenAlex response must be a JSON object")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 4:
                    break
                time.sleep(min(2**attempt, 8))
        raise RuntimeError("OpenAlex request failed after retries") from last_error


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run targeted retrospective calibration")
    parser.add_argument("--cases", default="validation/retrospective_cases.yaml")
    parser.add_argument("--output", default="validation/results/retrospective-v0.4.json")
    parser.add_argument("--sample-size", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = config.get("cases") if isinstance(config, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrospective config must contain non-empty cases list")

    client = OpenAlexHistoryClient(sample_size=args.sample_size)
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
        "methodology": {
            "discovery_query": "broad query retained in case definition for audit/discovery",
            "historical_query": "targeted quoted/Boolean query derived from the discovered semantic cluster",
            "membership_gate": "representative results must still pass alias/context or very strong semantic-anchor gate",
            "github_history": "excluded until first relevant commit/release/tag can be timestamp-verified",
            "pre_origin_boundary": "a monthly bucket counts as pre-origin only when the entire bucket ends before the known origin date",
        },
        "cases": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({result["id"]: result["summary"] for result in results}, ensure_ascii=False, indent=2))


def run_case(
    case: dict[str, Any],
    *,
    client: OpenAlexHistoryClient,
    scorer: EmergingScorer,
) -> dict[str, Any]:
    case_id = _required_str(case, "id")
    start = date.fromisoformat(_required_str(case, "validation_start"))
    milestone = date.fromisoformat(_required_str(case["milestone"], "date"))
    origin = date.fromisoformat(_required_str(case["origin"], "date"))
    semantic = case.get("semantic_filter") if isinstance(case.get("semantic_filter"), dict) else {}
    anchor = _required_str(semantic, "anchor")
    historical_query = _required_str(semantic, "historical_query")
    aliases = tuple(str(value) for value in semantic.get("aliases", []) if str(value).strip())
    context_terms = tuple(str(value) for value in semantic.get("context_terms", []) if str(value).strip())

    curve: list[dict[str, Any]] = []
    windows = list(month_windows(start, milestone))
    for index, window in enumerate(windows, start=1):
        print(f"[{case_id}] {index}/{len(windows)} {window.key}", flush=True)
        openalex = client.month(historical_query, window)
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

    first_raw = next((row["period"] for row in curve if row["raw_research_count"] > 0), None)
    pre_origin_raw_count = sum(
        row["raw_research_count"]
        for row in curve
        if date.fromisoformat(row["end"]) < origin
    )
    pre_origin_count = sum(
        row["total_count"]
        for row in curve
        if date.fromisoformat(row["end"]) < origin
    )

    timeline: list[dict[str, Any]] = []
    for end_index, row in enumerate(curve):
        prefix = curve[: end_index + 1]
        first_sustained = first_sustained_period(prefix)
        if first_sustained is None:
            timeline.append({"period": row["period"], "score": None, "reason": "no_sustained_signal_yet"})
            continue
        state = aggregate_state(case, prefix, first_sustained=first_sustained)
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
    lead_months = lead_months_to(first_useful, milestone) if first_useful else None

    return {
        "id": case_id,
        "label": case.get("label"),
        "profile": case.get("profile"),
        "origin": case.get("origin"),
        "milestone": case.get("milestone"),
        "preregistered_expectation": expectation,
        "queries": {
            "discovery_openalex": case.get("openalex_query"),
            "targeted_historical_openalex": historical_query,
            "github_discovery": case.get("github_query"),
        },
        "summary": {
            "first_raw_activity": first_raw,
            "first_semantic_activity": first_active_period(curve),
            "first_sustained_activity": first_sustained_period(curve),
            "first_useful_signal": first_useful,
            "lead_months": lead_months,
            "target_met": lead_months is not None and lead_months >= target_lead,
            "pre_origin_raw_count": pre_origin_raw_count,
            "pre_origin_count": pre_origin_count,
        },
        "curve": curve,
        "score_timeline": timeline,
    }


def aggregate_state(
    case: dict[str, Any], curve: list[dict[str, Any]], *, first_sustained: str
) -> TrendState:
    active = [row for row in curve if row["total_count"] > 0]
    if not active:
        raise ValueError("cannot aggregate empty historical signal")

    periods: dict[str, PeriodBucket] = {}
    research_total = 0
    actor_keys: set[str] = set()
    for row in curve:
        research = int(row["research_count"])
        if research:
            periods[row["period"]] = PeriodBucket(
                period=row["period"],
                total=research,
                by_evidence_type={"research": research},
                by_provider={"openalex": research},
            )
        research_total += research
        actor_keys.update(row["openalex"].get("accepted_sample_actors") or [])

    last_active = active[-1]["period"] + "-01T00:00:00Z"
    first_research = first_provider_period(curve, "research_count") + "-01T00:00:00Z"
    return TrendState(
        trend_id=f"retrospective:{_required_str(case, 'id')}",
        profile=_required_str(case, "profile"),
        technology_direction=_required_str(case, "technology_direction"),
        embedding_model="retrospective-targeted-semantic-gate",
        centroid=(1.0, 0.0),
        first_seen=first_sustained + "-01T00:00:00Z",
        last_seen=last_active,
        created_at=last_active,
        updated_at=last_active,
        observation_ids={f"aggregate:{index}" for index in range(research_total)},
        evidence_counts={"research": research_total},
        provider_counts={"openalex": research_total},
        artifact_counts={"paper": research_total},
        actor_keys=actor_keys,
        first_evidence_at={"research": first_research},
        periods=periods,
    )


def _accepted_sample_actors(samples: list[dict[str, Any]], gate: SampleGateResult) -> list[str]:
    actors: set[str] = set()
    for index in gate.accepted_indices:
        if index < len(samples):
            values = samples[index].get("actor_keys")
            if isinstance(values, list):
                actors.update(str(value) for value in values if str(value).strip())
    return sorted(actors)


def month_windows(start: date, end: date):
    cursor = start.replace(day=1)
    end_month = end.replace(day=1)
    while cursor <= end_month:
        next_month = shift_month(cursor, 1)
        yield MonthWindow(
            key=f"{cursor.year:04d}-{cursor.month:02d}",
            start=cursor,
            end=min(end, next_month - timedelta(days=1)),
        )
        cursor = next_month


def first_active_period(curve: list[dict[str, Any]]) -> str | None:
    return next((row["period"] for row in curve if row["total_count"] > 0), None)


def first_sustained_period(curve: list[dict[str, Any]]) -> str | None:
    for index, row in enumerate(curve):
        if row["total_count"] <= 0:
            continue
        local = curve[index : min(len(curve), index + 3)]
        if sum(1 for item in local if item["total_count"] > 0) >= 2:
            return row["period"]
    return None


def first_provider_period(curve: list[dict[str, Any]], field: str) -> str:
    for row in curve:
        if int(row[field]) > 0:
            return str(row["period"])
    raise ValueError(f"no active period for {field}")


def lead_months_to(signal_period: str, milestone: date) -> int:
    signal = date.fromisoformat(signal_period + "-01")
    target = milestone.replace(day=1)
    return (target.year - signal.year) * 12 + target.month - signal.month


def shift_month(value: date, offset: int) -> date:
    total = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


if __name__ == "__main__":
    main()
