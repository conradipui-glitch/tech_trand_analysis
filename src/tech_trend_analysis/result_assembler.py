from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Mapping, Sequence

from .scoring import EmergingScoreResult, EmergingScorer, SCORE_VERSION
from .trend_state import TrendState


RESULT_SCHEMA_VERSION = "0.2.0"
METHODOLOGY_VERSION = "0.2.0"
TOP_LIMIT = 15

_EVIDENCE_PRIORITY = {
    "adoption": 90,
    "product": 85,
    "implementation": 80,
    "patent": 70,
    "research": 60,
    "investment": 50,
    "regulation": 40,
    "analysis": 30,
    "other": 10,
}


@dataclass(frozen=True, slots=True)
class CoverageStatus:
    attempted: tuple[str, ...] = ()
    succeeded: tuple[str, ...] = ()
    failed: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, list[str]]:
        return {
            "attempted": sorted(set(self.attempted)),
            "succeeded": sorted(set(self.succeeded)),
            "failed": sorted(set(self.failed)),
        }


@dataclass(frozen=True, slots=True)
class RankedCandidate:
    state: TrendState
    score: EmergingScoreResult
    observations: tuple[dict[str, Any], ...]


def assemble_trend_analysis(
    *,
    technology_direction: str,
    source_profile: str,
    candidates: Sequence[TrendState],
    observations_by_id: Mapping[str, dict[str, Any]],
    as_of: date,
    scorer: EmergingScorer | None = None,
    normalized_direction: str | None = None,
    coverage: CoverageStatus | None = None,
    generated_at: str | None = None,
    methodology_version: str = METHODOLOGY_VERSION,
) -> dict[str, Any]:
    """Build the machine-readable TOP-15 from already discovered TrendStates.

    This layer never discovers trends and never asks an LLM to choose the ranking.
    It scores the supplied durable semantic states, sorts them deterministically,
    attaches only representative evidence that already exists in ObservationStore,
    and fails closed for narrative fields that still require grounded enrichment.
    """
    direction = technology_direction.strip()
    profile = source_profile.strip()
    if not direction:
        raise ValueError("technology_direction must be non-empty")
    if not profile:
        raise ValueError("source_profile must be non-empty")

    resolved_scorer = scorer or EmergingScorer()
    warnings: list[str] = []
    ranked: list[RankedCandidate] = []

    for state in candidates:
        if state.profile != profile:
            warnings.append(f"Skipped {state.trend_id}: profile {state.profile!r} does not match {profile!r}.")
            continue
        observations = tuple(
            observations_by_id[observation_id]
            for observation_id in sorted(state.observation_ids)
            if observation_id in observations_by_id
            and _is_source_eligible(observations_by_id[observation_id])
        )
        if not observations:
            warnings.append(f"Skipped {state.trend_id}: no representative source with a canonical URL is available.")
            continue
        ranked.append(
            RankedCandidate(
                state=state,
                score=resolved_scorer.score(state, as_of=as_of),
                observations=observations,
            )
        )

    ranked.sort(
        key=lambda item: (
            -item.score.total,
            -item.score.confidence,
            -item.state.observation_count,
            item.state.trend_id,
        )
    )
    selected = ranked[:TOP_LIMIT]

    if not selected:
        status = "insufficient_evidence"
    elif len(selected) < TOP_LIMIT:
        status = "partial"
        warnings.append(
            f"Only {len(selected)} evidence-backed trend candidates are currently available; TOP-{TOP_LIMIT} is not padded with generated items."
        )
    else:
        status = "ok"

    providers_used = sorted(
        {
            provider
            for item in selected
            for provider, count in item.state.provider_counts.items()
            if count > 0
        }
    )
    observation_ids = {
        observation_id
        for item in selected
        for observation_id in item.state.observation_ids
    }
    coverage_status = coverage or CoverageStatus(
        attempted=tuple(providers_used),
        succeeded=tuple(providers_used),
        failed=(),
    )

    trends = [
        _trend_contract(rank=index, candidate=item)
        for index, item in enumerate(selected, start=1)
    ]
    coverage_start = min((_date_part(item.state.first_seen) for item in selected), default=None)
    generated = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "request": {
            "technology_direction": direction,
            "normalized_direction": normalized_direction,
            "source_profile": profile,
            "generated_at": generated,
            "methodology_version": methodology_version,
            "requested_limit": TOP_LIMIT,
            "coverage_start": coverage_start,
            "coverage_end": as_of.isoformat(),
        },
        "summary": {
            "status": status,
            "trend_count": len(trends),
            "candidate_count": len(candidates),
            "observation_count": len(observation_ids),
            "providers_used": providers_used,
            "coverage": coverage_status.to_dict(),
            "warnings": warnings,
        },
        "trends": trends,
    }


def _trend_contract(*, rank: int, candidate: RankedCandidate) -> dict[str, Any]:
    state = candidate.state
    score = candidate.score
    ordered = sorted(candidate.observations, key=_representative_sort_key, reverse=True)
    sources = [_source_ref(observation) for observation in ordered[:5]]
    primary = ordered[0]
    primary_source = sources[0]
    name = _candidate_name(primary, state)
    description = _candidate_description(primary, name)

    return {
        "rank": rank,
        "trend_id": state.trend_id,
        "name": name,
        "description": description,
        "stage": score.stage,
        "score": score.to_contract(),
        "first_seen": {
            "period": _month_part(state.first_seen),
            "method": "first_persistent_semantic_cluster",
            "confidence": round(score.confidence, 4),
        },
        "motivation": {
            "problem": "Недостаточно подтверждённых evidence-данных для вывода о проблеме; требуется grounded enrichment.",
            "advantage": "Недостаточно подтверждённых evidence-данных для вывода о преимуществе; требуется grounded enrichment.",
        },
        "case_example": {
            "name": primary_source["title"],
            "kind": str(primary.get("artifact_kind") or primary_source["evidence_type"]),
            "description": _candidate_description(primary, primary_source["title"]),
            "source": primary_source,
        },
        "evidence_summary": {
            "total": state.observation_count,
            "by_type": dict(sorted(state.evidence_counts.items())),
            "actor_count": state.actor_diversity,
            "provider_count": state.provider_diversity,
            "country_count": _country_count(candidate.observations),
        },
        "trajectory": [
            {
                "period": bucket.period,
                "total": bucket.total,
                "by_evidence_type": dict(sorted(bucket.by_evidence_type.items())),
            }
            for _, bucket in sorted(state.periods.items())[-12:]
        ],
        "representative_sources": sources,
        "methodology_explanation": _methodology_explanation(score),
        "limitations": [
            "Ranking is deterministic from TrendState + Emerging Score; no LLM selected or reordered this candidate.",
            "Problem/advantage narrative remains fail-closed until grounded enrichment is attached.",
            f"Score methodology={score.version}; result assembler={METHODOLOGY_VERSION}.",
        ],
    }


def _source_ref(observation: Mapping[str, Any]) -> dict[str, Any]:
    actors = observation.get("actors") if isinstance(observation.get("actors"), list) else []
    actor = None
    if actors and isinstance(actors[0], Mapping):
        value = actors[0].get("name")
        actor = str(value).strip() if value else None
    published = observation.get("published_at")
    return {
        "observation_id": str(observation.get("observation_id") or "") or None,
        "provider": str(observation.get("provider") or "unknown"),
        "evidence_type": str(observation.get("evidence_type") or "other"),
        "title": str(observation.get("title") or "Untitled evidence").strip(),
        "url": str(observation.get("canonical_url") or "").strip(),
        "date": _date_part(str(published)) if published else None,
        "actor": actor,
        "why_representative": "Representative evidence already assigned to this semantic TrendState.",
    }


def _representative_sort_key(observation: Mapping[str, Any]) -> tuple[int, int, str]:
    evidence = str(observation.get("evidence_type") or "other")
    metrics = observation.get("metrics") if isinstance(observation.get("metrics"), Mapping) else {}
    activity = 0
    for key in ("stars", "citations", "cited_by_count", "forks"):
        value = metrics.get(key)
        if isinstance(value, (int, float)):
            activity += int(value)
    published = str(observation.get("published_at") or "")
    return (_EVIDENCE_PRIORITY.get(evidence, 0), activity, published)


def _candidate_name(observation: Mapping[str, Any], state: TrendState) -> str:
    analysis = observation.get("analysis") if isinstance(observation.get("analysis"), Mapping) else {}
    labels = analysis.get("technology_labels") if isinstance(analysis.get("technology_labels"), list) else []
    for label in labels:
        if isinstance(label, str) and label.strip():
            return label.strip()[:180]
    title = str(observation.get("title") or "").strip()
    return (title or state.technology_direction)[:180]


def _candidate_description(observation: Mapping[str, Any], fallback: str) -> str:
    text = str(observation.get("text") or "").strip()
    if not text:
        text = fallback
    return text[:600]


def _methodology_explanation(score: EmergingScoreResult) -> str:
    c = score.components
    return (
        f"Emerging Score {score.total:.1f}/100 (confidence {score.confidence:.2f}, stage={score.stage}) from durable semantic TrendState. "
        f"Growth={c['growth'].value:.1f}, acceleration={c['acceleration'].value:.1f}, novelty={c['novelty'].value:.1f}, "
        f"evidence diversity={c['evidence_diversity'].value:.1f}, actor diversity={c['actor_diversity'].value:.1f}, "
        f"persistence={c['persistence'].value:.1f}, maturity penalty={c['maturity_penalty'].value:.1f}. "
        "Provider retrieval does not itself create a trend; evidence must already belong to the semantic cluster."
    )


def _country_count(observations: Sequence[Mapping[str, Any]]) -> int | None:
    countries: set[str] = set()
    for observation in observations:
        actors = observation.get("actors") if isinstance(observation.get("actors"), list) else []
        for actor in actors:
            if not isinstance(actor, Mapping):
                continue
            country = actor.get("country")
            if isinstance(country, str) and country.strip():
                countries.add(country.strip().upper())
    return len(countries) if countries else None


def _is_source_eligible(observation: Mapping[str, Any]) -> bool:
    return bool(
        str(observation.get("title") or "").strip()
        and str(observation.get("canonical_url") or "").strip()
        and str(observation.get("provider") or "").strip()
        and str(observation.get("evidence_type") or "").strip()
    )


def _date_part(value: str) -> str:
    return value[:10]


def _month_part(value: str) -> str:
    return value[:7]
