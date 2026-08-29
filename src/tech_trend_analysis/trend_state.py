from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np

from .clustering import Microcluster, MicroclusteringResult


TREND_STATE_VERSION = "0.1.0"


class TrendStateConflictError(RuntimeError):
    """Raised when one microcluster bridges multiple existing trend identities."""


@dataclass(slots=True)
class PeriodBucket:
    period: str
    total: int = 0
    by_evidence_type: dict[str, int] = field(default_factory=dict)
    by_provider: dict[str, int] = field(default_factory=dict)

    def add(self, *, evidence_type: str, provider: str) -> None:
        self.total += 1
        self.by_evidence_type[evidence_type] = self.by_evidence_type.get(evidence_type, 0) + 1
        self.by_provider[provider] = self.by_provider.get(provider, 0) + 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "period": self.period,
            "total": self.total,
            "by_evidence_type": dict(sorted(self.by_evidence_type.items())),
            "by_provider": dict(sorted(self.by_provider.items())),
        }


@dataclass(slots=True)
class TrendState:
    trend_id: str
    profile: str
    technology_direction: str
    embedding_model: str
    centroid: tuple[float, ...]
    first_seen: str
    last_seen: str
    created_at: str
    updated_at: str
    observation_ids: set[str] = field(default_factory=set)
    microcluster_ids: set[str] = field(default_factory=set)
    evidence_counts: dict[str, int] = field(default_factory=dict)
    provider_counts: dict[str, int] = field(default_factory=dict)
    artifact_counts: dict[str, int] = field(default_factory=dict)
    actor_keys: set[str] = field(default_factory=set)
    first_evidence_at: dict[str, str] = field(default_factory=dict)
    periods: dict[str, PeriodBucket] = field(default_factory=dict)
    update_count: int = 0
    version: str = TREND_STATE_VERSION

    @property
    def observation_count(self) -> int:
        return len(self.observation_ids)

    @property
    def evidence_diversity(self) -> int:
        return len(self.evidence_counts)

    @property
    def provider_diversity(self) -> int:
        return len(self.provider_counts)

    @property
    def actor_diversity(self) -> int:
        return len(self.actor_keys)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "trend_id": self.trend_id,
            "profile": self.profile,
            "technology_direction": self.technology_direction,
            "embedding_model": self.embedding_model,
            "centroid": list(self.centroid),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "observation_count": self.observation_count,
            "observation_ids": sorted(self.observation_ids),
            "microcluster_ids": sorted(self.microcluster_ids),
            "evidence_counts": dict(sorted(self.evidence_counts.items())),
            "provider_counts": dict(sorted(self.provider_counts.items())),
            "artifact_counts": dict(sorted(self.artifact_counts.items())),
            "actor_diversity": self.actor_diversity,
            "actor_keys": sorted(self.actor_keys),
            "first_evidence_at": dict(sorted(self.first_evidence_at.items())),
            "periods": [self.periods[key].to_dict() for key in sorted(self.periods)],
            "update_count": self.update_count,
        }


@dataclass(frozen=True, slots=True)
class TrendAssignment:
    microcluster_id: str
    trend_id: str
    reason: str
    similarity: float | None
    new_observation_count: int


@dataclass(frozen=True, slots=True)
class TrendStateUpdateResult:
    assignments: tuple[TrendAssignment, ...]
    created_trend_ids: tuple[str, ...]
    updated_trend_ids: tuple[str, ...]


class TrendStateManager:
    """Own durable trend identity across conservative batch microclusters.

    Matching order is intentionally conservative:
    1. Existing observation ownership wins and makes rolling re-collection idempotent.
    2. If a microcluster bridges observations owned by multiple trends, fail closed.
    3. Otherwise match to an existing centroid within the same profile/direction.
    4. If similarity is below threshold, create a new long-lived TrendState.

    The similarity threshold is deliberately configurable and remains a calibration
    parameter until retrospective B-030 tests are available.
    """

    def __init__(self, *, match_similarity_threshold: float = 0.82) -> None:
        if not 0 < match_similarity_threshold <= 1:
            raise ValueError("match_similarity_threshold must be in (0, 1]")
        self.match_similarity_threshold = match_similarity_threshold
        self.states: dict[str, TrendState] = {}
        self.observation_to_trend: dict[str, str] = {}

    def ingest(
        self,
        result: MicroclusteringResult,
        observations_by_id: Mapping[str, dict[str, Any]],
        *,
        now: str | None = None,
    ) -> TrendStateUpdateResult:
        resolved_now = _canonical_time(now or _utc_now_iso())
        created: list[str] = []
        updated: set[str] = set()
        assignments: list[TrendAssignment] = []

        # Match all clusters against the state snapshot that existed at the start
        # of this ingest. Newly created trends do not absorb sibling microclusters
        # from the same batch merely because the batch was over-segmented.
        snapshot_ids = tuple(self.states)
        plans: list[tuple[Microcluster, str | None, str, float | None]] = []

        for cluster in result.clusters:
            observations = _cluster_observations(cluster, observations_by_id)
            direction = _single_direction(observations)
            owned = {
                self.observation_to_trend[observation_id]
                for observation_id in cluster.member_ids
                if observation_id in self.observation_to_trend
            }
            if len(owned) > 1:
                raise TrendStateConflictError(
                    f"microcluster {cluster.cluster_id} bridges existing trends: {sorted(owned)}"
                )
            if len(owned) == 1:
                plans.append((cluster, next(iter(owned)), "existing_observation", None))
                continue

            matched_id, similarity = self._best_centroid_match(
                cluster=cluster,
                profile=result.profile,
                direction=direction,
                embedding_model=result.embedding_model,
                candidate_ids=snapshot_ids,
            )
            if matched_id is not None and similarity is not None:
                plans.append((cluster, matched_id, "centroid", similarity))
            else:
                plans.append((cluster, None, "new", similarity))

        for cluster, target_id, reason, similarity in plans:
            observations = _cluster_observations(cluster, observations_by_id)
            direction = _single_direction(observations)
            if target_id is None:
                target_id = _new_trend_id(
                    profile=result.profile,
                    direction=direction,
                    first_cluster_id=cluster.cluster_id,
                    first_seen=min(_event_time(observation) for observation in observations),
                )
                if target_id in self.states:
                    # Deterministic replay of the same first cluster should resolve
                    # to the existing identity rather than overwrite it.
                    reason = "deterministic_replay"
                else:
                    first_event = min(_event_time(observation) for observation in observations)
                    last_event = max(_event_time(observation) for observation in observations)
                    self.states[target_id] = TrendState(
                        trend_id=target_id,
                        profile=result.profile,
                        technology_direction=direction,
                        embedding_model=result.embedding_model,
                        centroid=tuple(float(value) for value in _normalized(cluster.centroid)),
                        first_seen=first_event,
                        last_seen=last_event,
                        created_at=resolved_now,
                        updated_at=resolved_now,
                    )
                    created.append(target_id)

            state = self.states[target_id]
            new_count = self._apply_cluster(
                state=state,
                cluster=cluster,
                observations=observations,
                now=resolved_now,
            )
            if target_id not in created and new_count > 0:
                updated.add(target_id)
            assignments.append(
                TrendAssignment(
                    microcluster_id=cluster.cluster_id,
                    trend_id=target_id,
                    reason=reason,
                    similarity=similarity,
                    new_observation_count=new_count,
                )
            )

        return TrendStateUpdateResult(
            assignments=tuple(assignments),
            created_trend_ids=tuple(created),
            updated_trend_ids=tuple(sorted(updated)),
        )

    def _best_centroid_match(
        self,
        *,
        cluster: Microcluster,
        profile: str,
        direction: str,
        embedding_model: str,
        candidate_ids: tuple[str, ...],
    ) -> tuple[str | None, float | None]:
        incoming = _normalized(cluster.centroid)
        best_id: str | None = None
        best_similarity: float | None = None
        direction_key = _direction_key(direction)

        for trend_id in candidate_ids:
            state = self.states[trend_id]
            if state.profile != profile:
                continue
            if _direction_key(state.technology_direction) != direction_key:
                continue
            if state.embedding_model != embedding_model:
                continue
            existing = np.asarray(state.centroid, dtype=np.float32)
            if existing.shape != incoming.shape:
                continue
            similarity = float(np.clip(existing @ incoming, -1.0, 1.0))
            if best_similarity is None or similarity > best_similarity:
                best_id = trend_id
                best_similarity = similarity

        if best_similarity is None or best_similarity < self.match_similarity_threshold:
            return None, best_similarity
        return best_id, best_similarity

    def _apply_cluster(
        self,
        *,
        state: TrendState,
        cluster: Microcluster,
        observations: list[dict[str, Any]],
        now: str,
    ) -> int:
        if state.profile is None:
            raise ValueError("trend state profile must be set")
        incoming_by_id = {
            _required_string(observation, "observation_id"): observation
            for observation in observations
        }
        new_ids = [
            observation_id
            for observation_id in cluster.member_ids
            if observation_id not in state.observation_ids
        ]

        # A repeated rolling-window collection must be a no-op for counters.
        if not new_ids:
            state.microcluster_ids.add(cluster.cluster_id)
            return 0

        old_count = state.observation_count
        new_count = len(new_ids)
        if old_count > 0:
            old_centroid = np.asarray(state.centroid, dtype=np.float32)
            incoming_centroid = _normalized(cluster.centroid)
            combined = old_centroid * old_count + incoming_centroid * new_count
            state.centroid = tuple(float(value) for value in _normalized(combined))
        else:
            state.centroid = tuple(float(value) for value in _normalized(cluster.centroid))

        for observation_id in new_ids:
            observation = incoming_by_id[observation_id]
            previous_owner = self.observation_to_trend.get(observation_id)
            if previous_owner is not None and previous_owner != state.trend_id:
                raise TrendStateConflictError(
                    f"observation {observation_id} already belongs to {previous_owner}"
                )

            event_time = _event_time(observation)
            evidence_type = _required_string(observation, "evidence_type")
            provider = _required_string(observation, "provider")
            artifact_kind = _required_string(observation, "artifact_kind")

            state.observation_ids.add(observation_id)
            self.observation_to_trend[observation_id] = state.trend_id
            state.first_seen = min(state.first_seen, event_time)
            state.last_seen = max(state.last_seen, event_time)
            state.evidence_counts[evidence_type] = state.evidence_counts.get(evidence_type, 0) + 1
            state.provider_counts[provider] = state.provider_counts.get(provider, 0) + 1
            state.artifact_counts[artifact_kind] = state.artifact_counts.get(artifact_kind, 0) + 1
            previous_first = state.first_evidence_at.get(evidence_type)
            if previous_first is None or event_time < previous_first:
                state.first_evidence_at[evidence_type] = event_time

            for actor_key in _actor_keys(observation):
                state.actor_keys.add(actor_key)

            period = _month_bucket(event_time)
            bucket = state.periods.setdefault(period, PeriodBucket(period=period))
            bucket.add(evidence_type=evidence_type, provider=provider)

        state.microcluster_ids.add(cluster.cluster_id)
        state.updated_at = now
        state.update_count += 1
        return new_count


def _cluster_observations(
    cluster: Microcluster,
    observations_by_id: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    missing = [member_id for member_id in cluster.member_ids if member_id not in observations_by_id]
    if missing:
        raise KeyError(f"missing observations for microcluster {cluster.cluster_id}: {missing}")
    observations = [observations_by_id[member_id] for member_id in cluster.member_ids]
    for observation in observations:
        if not isinstance(observation, dict):
            raise TypeError("observations_by_id values must be dict objects")
    return observations


def _single_direction(observations: list[dict[str, Any]]) -> str:
    values: dict[str, str] = {}
    for observation in observations:
        context = observation.get("collection_context")
        if not isinstance(context, dict):
            raise ValueError("Observation missing collection_context")
        direction = context.get("technology_direction")
        if not isinstance(direction, str) or not direction.strip():
            raise ValueError("Observation missing technology_direction")
        values[_direction_key(direction)] = direction.strip()
    if len(values) != 1:
        raise ValueError(f"microcluster contains multiple technology directions: {sorted(values.values())}")
    return next(iter(values.values()))


def _event_time(observation: dict[str, Any]) -> str:
    for key in ("published_at", "observed_at"):
        value = observation.get(key)
        if isinstance(value, str) and value.strip():
            return _canonical_time(value)
    raise ValueError("Observation needs published_at or observed_at")


def _canonical_time(value: str) -> str:
    raw = value.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw = raw + "T00:00:00Z"
    normalized = raw.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed.isoformat().replace("+00:00", "Z")


def _month_bucket(event_time: str) -> str:
    return event_time[:7]


def _actor_keys(observation: dict[str, Any]) -> set[str]:
    actors = observation.get("actors")
    if not isinstance(actors, list):
        return set()
    result: set[str] = set()
    for actor in actors:
        if not isinstance(actor, dict):
            continue
        kind = str(actor.get("kind") or "unknown").strip().casefold()
        external_id = actor.get("external_id")
        name = actor.get("name")
        if isinstance(external_id, str) and external_id.strip():
            result.add(f"{kind}:id:{external_id.strip().casefold()}")
        elif isinstance(name, str) and name.strip():
            result.add(f"{kind}:name:{' '.join(name.casefold().split())}")
    return result


def _normalized(values: Any) -> np.ndarray:
    vector = np.asarray(values, dtype=np.float32)
    if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("centroid must be a finite non-empty 1D vector")
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("centroid must be non-zero")
    return vector / norm


def _direction_key(value: str) -> str:
    return " ".join(value.casefold().split())


def _new_trend_id(*, profile: str, direction: str, first_cluster_id: str, first_seen: str) -> str:
    payload = "\n".join([profile, _direction_key(direction), first_seen, first_cluster_id])
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"trend:{profile}:{digest}"


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
