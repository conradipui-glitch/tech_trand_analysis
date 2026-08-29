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
GITHUB_SEARCH_URL = "https://api.github.com/search/repositories"


@dataclass(frozen=True, slots=True)
class MonthWindow:
    key: str
    start: date
    end: date


class PublicHistoryClient:
    def __init__(self, *, github_token: str, sample_size: int = 10) -> None:
        if not github_token:
            raise ValueError("GITHUB_TOKEN is required for retrospective validation")
        self.sample_size = sample_size
        self.client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "tech-trend-analysis-retrospective/0.2"},
        )
        self.github_headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def close(self) -> None:
        self.client.close()

    def openalex_month(self, query: str, window: MonthWindow) -> dict[str, Any]:
        params = {
            "search": query,
            "filter": (
                f"from_publication_date:{window.start.isoformat()},"
                f"to_publication_date:{window.end.isoformat()}"
            ),
            "per-page": self.sample_size,
        }
        payload = self._get_json(OPENALEX_URL, params=params)
        meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
        results = payload.get("results") if isinstance(payload.get("results"), list) else []
        actors: set[str] = set()
        samples: list[dict[str, Any]] = []
        for work in results:
            if not isinstance(work, dict):
                continue
            work_actors: set[str] = set()
            authorships = work.get("authorships")
            if isinstance(authorships, list):
                for authorship in authorships:
                    if not isinstance(authorship, dict):
                        continue
                    institutions = authorship.get("institutions")
                    if isinstance(institutions, list):
                        for institution in institutions:
                            if not isinstance(institution, dict):
                                continue
                            actor_id = institution.get("id") or institution.get("display_name")
                            if isinstance(actor_id, str) and actor_id.strip():
                                work_actors.add(f"openalex:institution:{actor_id.strip()}")
                    author = authorship.get("author")
                    if isinstance(author, dict):
                        actor_id = author.get("id") or author.get("display_name")
                        if isinstance(actor_id, str) and actor_id.strip():
                            work_actors.add(f"openalex:author:{actor_id.strip()}")
            actors.update(work_actors)
            samples.append(
                {
                    "id": work.get("id"),
                    "title": work.get("title") or work.get("display_name"),
                    "date": work.get("publication_date"),
                    "actor_keys": sorted(work_actors),
                }
            )

        return {
            "count": int(meta.get("count") or 0),
            "sample_actors": sorted(actors),
            "samples": samples,
        }

    def github_month(self, query: str, window: MonthWindow) -> dict[str, Any]:
        q = f"{query} created:{window.start.isoformat()}..{window.end.isoformat()}"
        payload = self._get_json(
            GITHUB_SEARCH_URL,
            params={"q": q, "per_page": self.sample_size, "sort": "stars", "order": "desc"},
            headers=self.github_headers,
        )
        items = payload.get("items") if isinstance(payload.get("items"), list) else []
        actors: set[str] = set()
        samples: list[dict[str, Any]] = []
        for repo in items:
            if not isinstance(repo, dict):
                continue
            repo_actors: set[str] = set()
            owner = repo.get("owner")
            if isinstance(owner, dict):
                login = owner.get("login")
                if isinstance(login, str) and login.strip():
                    repo_actors.add(f"github:owner:{login.strip().casefold()}")
            actors.update(repo_actors)
            samples.append(
                {
                    "id": repo.get("id"),
                    "full_name": repo.get("full_name"),
                    "description": repo.get("description"),
                    "created_at": repo.get("created_at"),
                    "stars": repo.get("stargazers_count"),
                    "actor_keys": sorted(repo_actors),
                }
            )

        count = int(payload.get("total_count") or 0)
        self._respect_github_search_limit()
        return {
            "count": count,
            "sample_actors": sorted(actors),
            "samples": samples,
            "query": q,
        }

    def _get_json(
        self,
        url: str,
        *,
        params: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(5):
            try:
                response = self.client.get(url, params=params, headers=headers)
                if response.status_code in {429, 500, 502, 503, 504}:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 16)
                    time.sleep(delay)
                    continue
                if response.status_code == 403 and "github.com" in url:
                    reset = response.headers.get("x-ratelimit-reset")
                    if reset and reset.isdigit():
                        delay = max(1.0, int(reset) - time.time() + 1.0)
                        time.sleep(min(delay, 70.0))
                        continue
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError(f"non-object JSON from {url}")
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == 4:
                    break
                time.sleep(min(2**attempt, 8))
        raise RuntimeError(f"request failed after retries: {url}") from last_error

    def _respect_github_search_limit(self) -> None:
        time.sleep(2.1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run preregistered retrospective trend validation")
    parser.add_argument("--cases", default="validation/retrospective_cases.yaml")
    parser.add_argument("--output", default="validation/results/retrospective-v0.2.json")
    parser.add_argument("--sample-size", type=int, default=10)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = yaml.safe_load(Path(args.cases).read_text(encoding="utf-8"))
    cases = config.get("cases") if isinstance(config, dict) else None
    if not isinstance(cases, list) or not cases:
        raise ValueError("retrospective config must contain non-empty cases list")

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    client = PublicHistoryClient(github_token=token, sample_size=args.sample_size)
    scorer = EmergingScorer()
    try:
        results = [run_case(case, client=client, scorer=scorer) for case in cases]
    finally:
        client.close()

    payload = {
        "validation_version": config.get("version"),
        "preregistered_at": config.get("preregistered_at"),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "count_semantics": {
            "raw_provider_total": "provider aggregate search count retained only for audit",
            "period_total": "cluster-conditioned estimate derived from representative provider samples and used for scoring",
            "single_match_rule": "one sampled semantic match is never amplified beyond one observation",
            "actor_diversity": "lower-bound estimate from actors attached to accepted representative samples only",
        },
        "methodology_warning": (
            "Phase-10 calibration evidence. Production targeted backfill uses vector-to-centroid membership gating. "
            "This retrospective runner cannot materialize every historical provider result, so it uses a conservative "
            "sample-based semantic proxy before aggregate counts enter TrendState. Raw counts and gate diagnostics remain auditable."
        ),
        "cases": results,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        result["id"]: {
            "first_raw_activity": result["summary"]["first_raw_activity"],
            "first_sustained_activity": result["summary"]["first_sustained_activity"],
            "first_useful_signal": result["summary"]["first_useful_signal"],
            "lead_months": result["summary"]["lead_months"],
            "target_met": result["summary"]["target_met"],
            "pre_origin_raw_count": result["summary"]["pre_origin_raw_count"],
            "pre_origin_count": result["summary"]["pre_origin_count"],
        }
        for result in results
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def run_case(case: dict[str, Any], *, client: PublicHistoryClient, scorer: EmergingScorer) -> dict[str, Any]:
    case_id = _required_str(case, "id")
    start = date.fromisoformat(_required_str(case, "validation_start"))
    milestone = date.fromisoformat(_required_str(case["milestone"], "date"))
    origin = date.fromisoformat(_required_str(case["origin"], "date"))
    windows = list(month_windows(start, milestone))
    semantic = case.get("semantic_filter") if isinstance(case.get("semantic_filter"), dict) else {}
    anchor = str(semantic.get("anchor") or case.get("label") or case.get("technology_direction") or "").strip()
    aliases = tuple(str(value) for value in semantic.get("aliases", []) if str(value).strip())
    context_terms = tuple(str(value) for value in semantic.get("context_terms", []) if str(value).strip())

    curve: list[dict[str, Any]] = []
    for index, window in enumerate(windows, start=1):
        print(f"[{case_id}] {index}/{len(windows)} {window.key}", flush=True)
        openalex = client.openalex_month(_required_str(case, "openalex_query"), window)
        github = client.github_month(_required_str(case, "github_query"), window)

        oa_gate = gate_sampled_count(
            raw_count=int(openalex["count"]),
            sample_texts=[str(item.get("title") or "") for item in openalex["samples"]],
            anchor_text=anchor,
            aliases=aliases,
            context_terms=context_terms,
        )
        gh_gate = gate_sampled_count(
            raw_count=int(github["count"]),
            sample_texts=[
                " ".join(
                    part for part in (str(item.get("full_name") or ""), str(item.get("description") or "")) if part.strip()
                )
                for item in github["samples"]
            ],
            anchor_text=anchor,
            aliases=aliases,
            context_terms=context_terms,
        )
        openalex["semantic_gate"] = oa_gate.to_dict()
        github["semantic_gate"] = gh_gate.to_dict()
        openalex["accepted_sample_actors"] = _accepted_sample_actors(openalex["samples"], oa_gate)
        github["accepted_sample_actors"] = _accepted_sample_actors(github["samples"], gh_gate)

        research = oa_gate.estimated_count
        implementation = gh_gate.estimated_count
        curve.append(
            {
                "period": window.key,
                "start": window.start.isoformat(),
                "end": window.end.isoformat(),
                "raw_research_count": int(openalex["count"]),
                "raw_implementation_count": int(github["count"]),
                "raw_total_count": int(openalex["count"]) + int(github["count"]),
                "research_count": research,
                "implementation_count": implementation,
                "total_count": research + implementation,
                "openalex": openalex,
                "github": github,
            }
        )

    first_raw = next((row["period"] for row in curve if row["raw_total_count"] > 0), None)
    pre_origin_raw_count = sum(
        row["raw_total_count"] for row in curve if date.fromisoformat(row["start"]) < origin
    )
    pre_origin_count = sum(
        row["total_count"] for row in curve if date.fromisoformat(row["start"]) < origin
    )

    timeline: list[dict[str, Any]] = []
    for end_index, row in enumerate(curve):
        prefix = curve[: end_index + 1]
        first_sustained = _first_sustained_period(prefix)
        if first_sustained is None:
            timeline.append({"period": row["period"], "score": None, "reason": "no_sustained_signal_yet"})
            continue
        state = _aggregate_state(case, prefix, first_sustained=first_sustained)
        score = scorer.score(state, as_of=date.fromisoformat(row["end"]))
        timeline.append(
            {
                "period": row["period"],
                "score": round(score.total, 4),
                "confidence": round(score.confidence, 4),
                "stage": score.stage,
                "components": {key: round(component.value, 4) for key, component in score.components.items()},
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
        "queries": {"openalex": case.get("openalex_query"), "github": case.get("github_query")},
        "semantic_filter": {"anchor": anchor, "aliases": list(aliases), "context_terms": list(context_terms)},
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


def _accepted_sample_actors(samples: list[dict[str, Any]], gate: SampleGateResult) -> list[str]:
    actors: set[str] = set()
    for index in gate.accepted_indices:
        if index >= len(samples):
            continue
        values = samples[index].get("actor_keys")
        if isinstance(values, list):
            actors.update(str(value) for value in values if str(value).strip())
    return sorted(actors)


def _aggregate_state(case: dict[str, Any], curve: list[dict[str, Any]], *, first_sustained: str) -> TrendState:
    active = [row for row in curve if row["total_count"] > 0]
    if not active:
        raise ValueError("cannot aggregate empty historical signal")

    periods: dict[str, PeriodBucket] = {}
    research_total = 0
    implementation_total = 0
    actor_keys: set[str] = set()
    for row in curve:
        research = int(row["research_count"])
        implementation = int(row["implementation_count"])
        total = research + implementation
        if total:
            bucket = PeriodBucket(period=row["period"], total=total)
            if research:
                bucket.by_evidence_type["research"] = research
                bucket.by_provider["openalex"] = research
            if implementation:
                bucket.by_evidence_type["implementation"] = implementation
                bucket.by_provider["github"] = implementation
            periods[row["period"]] = bucket
        research_total += research
        implementation_total += implementation
        actor_keys.update(row["openalex"].get("accepted_sample_actors") or row["openalex"].get("sample_actors") or [])
        actor_keys.update(row["github"].get("accepted_sample_actors") or row["github"].get("sample_actors") or [])

    observation_total = research_total + implementation_total
    evidence_counts: dict[str, int] = {}
    provider_counts: dict[str, int] = {}
    artifact_counts: dict[str, int] = {}
    first_evidence_at: dict[str, str] = {}
    if research_total:
        evidence_counts["research"] = research_total
        provider_counts["openalex"] = research_total
        artifact_counts["paper"] = research_total
        first_evidence_at["research"] = _first_provider_period(curve, "research_count") + "-01T00:00:00Z"
    if implementation_total:
        evidence_counts["implementation"] = implementation_total
        provider_counts["github"] = implementation_total
        artifact_counts["repository"] = implementation_total
        first_evidence_at["implementation"] = _first_provider_period(curve, "implementation_count") + "-01T00:00:00Z"

    last_active = active[-1]["period"] + "-01T00:00:00Z"
    return TrendState(
        trend_id=f"retrospective:{_required_str(case, 'id')}",
        profile=_required_str(case, "profile"),
        technology_direction=_required_str(case, "technology_direction"),
        embedding_model="retrospective-semantic-sample-gate",
        centroid=(1.0, 0.0),
        first_seen=first_sustained + "-01T00:00:00Z",
        last_seen=last_active,
        created_at=last_active,
        updated_at=last_active,
        observation_ids={f"aggregate:{index}" for index in range(observation_total)},
        evidence_counts=evidence_counts,
        provider_counts=provider_counts,
        artifact_counts=artifact_counts,
        actor_keys=actor_keys,
        first_evidence_at=first_evidence_at,
        periods=periods,
    )


def month_windows(start: date, end: date):
    cursor = start.replace(day=1)
    end_month = end.replace(day=1)
    while cursor <= end_month:
        next_month = _shift_month(cursor, 1)
        month_end = min(end, next_month - timedelta(days=1))
        yield MonthWindow(key=f"{cursor.year:04d}-{cursor.month:02d}", start=cursor, end=month_end)
        cursor = next_month


def _first_active_period(curve: list[dict[str, Any]]) -> str | None:
    return next((row["period"] for row in curve if row["total_count"] > 0), None)


def _first_sustained_period(curve: list[dict[str, Any]]) -> str | None:
    for index, row in enumerate(curve):
        if row["total_count"] <= 0:
            continue
        local = curve[index : min(len(curve), index + 3)]
        if sum(1 for item in local if item["total_count"] > 0) >= 2:
            return row["period"]
    return None


def _first_provider_period(curve: list[dict[str, Any]], field: str) -> str:
    for row in curve:
        if int(row[field]) > 0:
            return str(row["period"])
    raise ValueError(f"no active period for {field}")


def _lead_months(signal_period: str, milestone: date) -> int:
    signal = date.fromisoformat(signal_period + "-01")
    milestone_month = milestone.replace(day=1)
    return (milestone_month.year - signal.year) * 12 + milestone_month.month - signal.month


def _shift_month(value: date, offset: int) -> date:
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
