"""Attach historically verified GitHub implementation to an existing TrendState.

This is deliberately a post-discovery, post-clustering enrichment. Repository
creation time/current description are never accepted as historical evidence.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Sequence

import numpy as np

from .backfill import HistoricalGateResult, gate_historical_vectors
from .github_event_local_gate import evaluate_event_local
from .clustering import Microcluster, MicroclusteringResult, PROFILE_CONFIGS
from .sources.github_history import GitHubHistoryClient, GitHubHistoryQuery
from .trend_state import TrendStateManager, TrendStateUpdateResult


EmbeddingFn = Callable[[Sequence[str]], Sequence[Sequence[float]]]


@dataclass(frozen=True, slots=True)
class GitHubBridgePolicy:
    max_repositories_per_trend: int = 10
    similarity_threshold: float = 0.82
    experimental_event_local_threshold: float | None = None

    def __post_init__(self) -> None:
        if self.max_repositories_per_trend < 1:
            raise ValueError("max_repositories_per_trend must be >= 1")
        if not 0 < self.similarity_threshold <= 1:
            raise ValueError("similarity_threshold must be in (0, 1]")
        if self.experimental_event_local_threshold is not None and not 0 < self.experimental_event_local_threshold <= 1:
            raise ValueError("experimental_event_local_threshold must be in (0, 1]")


@dataclass(frozen=True, slots=True)
class GitHubBridgeResult:
    trend_id: str
    checked_repositories: tuple[str, ...]
    repositories_without_event: tuple[str, ...]
    verified_event_ids: tuple[str, ...]
    accepted_event_ids: tuple[str, ...]
    rejected_event_ids: tuple[str, ...]
    similarities: dict[str, float]
    accepted_observations: tuple[dict[str, Any], ...]
    update: TrendStateUpdateResult | None
    verified_observations: tuple[dict[str, Any], ...] = ()


class GitHubHistoryBridge:
    """Use existing cluster ownership to attach gated GitHub event evidence.

    The supplied embedder MUST use exactly the TrendState embedding model.
    Caller supplies cluster-specific, reviewed aliases/context: broad direction
    names or current repository descriptions alone are not historical proof.

    Only one earliest matching event per bounded repository is requested here.
    The result is the earliest VERIFIED event in the searched API window, not a
    universal first-ever implementation date.
    """

    def __init__(
        self,
        *,
        history_client: GitHubHistoryClient,
        embed: EmbeddingFn,
        embedding_model: str,
        policy: GitHubBridgePolicy | None = None,
    ) -> None:
        if not embedding_model.strip():
            raise ValueError("embedding_model must be nonempty")
        self.history_client = history_client
        self.embed = embed
        self.embedding_model = embedding_model
        self.policy = policy or GitHubBridgePolicy()

    def enrich(
        self,
        *,
        manager: TrendStateManager,
        trend_id: str,
        observations_by_id: Mapping[str, dict[str, Any]],
        aliases: Sequence[str],
        context_terms: Sequence[str] = (),
        distinctive_terms: Sequence[str] = (),
        now: datetime | None = None,
    ) -> GitHubBridgeResult:
        if trend_id not in manager.states:
            raise KeyError(f"unknown TrendState: {trend_id}")
        state = manager.states[trend_id]
        if state.embedding_model != self.embedding_model:
            raise ValueError("historical embeddings must use TrendState embedding_model")
        vetted_aliases = tuple(dict.fromkeys(term.strip() for term in aliases if term.strip()))
        vetted_distinctive = tuple(dict.fromkeys(term.strip() for term in distinctive_terms if term.strip()))
        if not vetted_aliases and not vetted_distinctive:
            raise ValueError("cluster-specific aliases or distinctive terms required")
        checked_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        if not np.isfinite(np.asarray(state.centroid, dtype=np.float64)).all():
            raise ValueError("invalid TrendState centroid")

        candidates: list[tuple[str, str]] = []
        for observation_id in sorted(state.observation_ids):
            observation = observations_by_id.get(observation_id)
            if not isinstance(observation, dict):
                continue
            if observation.get("provider") != "github" or observation.get("artifact_kind") != "repository":
                continue
            if observation.get("published_at") is not None:
                # We only anchor to present-day discovery, not historical guesses.
                continue
            repo = observation.get("external_id")
            context = observation.get("collection_context")
            if not isinstance(repo, str) or repo.count("/") != 1:
                continue
            if not isinstance(context, dict) or context.get("source_profile") != state.profile:
                continue
            if context.get("technology_direction", "").strip().casefold() != state.technology_direction.strip().casefold():
                continue
            if manager.observation_to_trend.get(observation_id) != trend_id:
                raise ValueError(f"repository is not owned by expected TrendState: {observation_id}")
            candidates.append((observation_id, repo))
        candidates = candidates[: self.policy.max_repositories_per_trend]

        events: list[tuple[str, dict[str, Any]]] = []
        no_event: list[str] = []
        observed_at = checked_at.replace(microsecond=0)
        for anchor_id, repository in candidates:
            query = GitHubHistoryQuery(
                repository=repository,
                technology_direction=state.technology_direction,
                source_profile=state.profile,
                aliases=vetted_aliases,
                context_terms=tuple(context_terms),
                distinctive_terms=vetted_distinctive,
                query_id=f"trend-history:{trend_id}",
            )
            if self.policy.experimental_event_local_threshold is not None and hasattr(self.history_client, "candidate_events"):
                repository_events = self.history_client.candidate_events(query)
            else:
                earliest = self.history_client.verify_earliest(query)
                repository_events = (earliest,) if earliest is not None else ()
            if not repository_events:
                no_event.append(repository)
                continue
            for event in repository_events:
                if event.repository != repository or event.event_kind not in {"commit", "release", "tag"}:
                    raise ValueError(f"untrusted historical event for {repository}")
                event_dt = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
                if event_dt.tzinfo is None or event_dt.astimezone(timezone.utc) > checked_at:
                    raise ValueError("historical event timestamp must be timezone-aware and not in the future")
                observation = event.to_observation(query, observed_at=observed_at)
                # Preserve stable actor identity instead of double-counting repo owner.
                anchor_actors = observations_by_id[anchor_id].get("actors")
                if isinstance(anchor_actors, list) and anchor_actors:
                    observation["actors"] = [dict(actor) for actor in anchor_actors]
                observation["metrics"]["historical_validation_scope"] = "bounded_repository_event_search"
                if observation["published_at"] != event.occurred_at or not observation["quality_flags"].get("historical_timestamp_verified"):
                    raise ValueError("historical Observation failed time provenance check")
                owner = manager.observation_to_trend.get(observation["observation_id"])
                if owner is not None and owner != trend_id:
                    raise ValueError("verified event is already owned by a different TrendState")
                events.append((anchor_id, observation))

        if not events:
            return GitHubBridgeResult(
                trend_id, tuple(repo for _, repo in candidates), tuple(no_event),
                (), (), (), {}, (), None
            )

        # The code path intentionally has NO TF-IDF fallback. If the embedding
        # model is unavailable or mismatched, fail instead of corrupting history.
        experimental = self.policy.experimental_event_local_threshold is not None
        decisions = [
            evaluate_event_local(
                technology_direction=state.technology_direction,
                title=obs["title"],
                text=obs.get("text") or "",
            )
            for _, obs in events
        ] if experimental else []
        texts = [
            (decision.evidence_span or _evidence_text(obs))
            for (_, obs), decision in zip(events, decisions, strict=True)
        ] if experimental else [_evidence_text(obs) for _, obs in events]
        vectors = np.asarray(self.embed(texts), dtype=np.float32)
        expected_dims = len(state.centroid)
        if vectors.shape != (len(events), expected_dims) or not np.isfinite(vectors).all():
            raise ValueError("embedder returned invalid shape or non-finite values")
        event_ids = [obs["observation_id"] for _, obs in events]
        if experimental:
            # Opt-in cross-modal research experiment only. This is distinct
            # from the historical centroid gate and is NOT a universal MVP
            # threshold; arbitrary technology families fail closed.
            anchor = np.asarray(self.embed([state.technology_direction]), dtype=np.float32)
            if anchor.shape != (1, expected_dims) or not np.isfinite(anchor).all():
                raise ValueError("direction embedder returned invalid shape")
            norms = np.linalg.norm(vectors, axis=1)
            anchor_norm = float(np.linalg.norm(anchor[0]))
            if anchor_norm == 0 or np.any(norms == 0):
                raise ValueError("experimental vectors must be non-zero")
            scores = (vectors @ anchor[0]) / (norms * anchor_norm)
            similarities = {
                obs_id: float(np.clip(score, -1, 1))
                for obs_id, score in zip(event_ids, scores, strict=True)
            }
            passed = [
                obs_id
                for obs_id, decision in zip(event_ids, decisions, strict=True)
                if decision.eligible and similarities[obs_id] >= self.policy.experimental_event_local_threshold
            ]
            accepted_ids = set(passed)
            gated = HistoricalGateResult(
                accepted_ids=tuple(passed),
                rejected_ids=tuple(obs_id for obs_id in event_ids if obs_id not in accepted_ids),
                similarities=similarities,
            )
        else:
            gated = gate_historical_vectors(
                state,
                observation_ids=event_ids,
                vectors=vectors,
                similarity_threshold=self.policy.similarity_threshold,
            )

        # A repository contributes at most ONE accepted implementation event:
        # earliest SEMANTICALLY accepted event in the bounded candidate window,
        # never the earliest mere lexical match. Later eligible events are
        # informational only; they must not amplify score/actor counts.
        accepted_candidates = set(gated.accepted_ids)
        chosen_by_repo: dict[str, str] = {}
        for _, observation in sorted(
            events,
            key=lambda item: (item[1]["published_at"], item[1]["observation_id"]),
        ):
            oid = observation["observation_id"]
            if oid not in accepted_candidates:
                continue
            repo_key = observation["relationships"][0]["target_id"]
            chosen_by_repo.setdefault(repo_key, oid)
        approved = set(chosen_by_repo.values())
        for _, observation in events:
            oid = observation["observation_id"]
            if oid in approved:
                observation["quality_flags"]["history_selection"] = "earliest_accepted_in_bounded_window"
            elif oid in accepted_candidates:
                observation["quality_flags"]["history_selection"] = "later_eligible_not_selected"
            else:
                observation["quality_flags"]["history_selection"] = "rejected_by_semantic_gate"
        gated = HistoricalGateResult(
            accepted_ids=tuple(oid for oid in event_ids if oid in approved),
            rejected_ids=tuple(oid for oid in event_ids if oid not in approved),
            similarities=gated.similarities,
        )
        clusters: list[Microcluster] = []
        observations_for_ingest: dict[str, dict[str, Any]] = {}
        accepted_observations: list[dict[str, Any]] = []
        for (anchor_id, observation), vector in zip(events, vectors, strict=True):
            event_id = observation["observation_id"]
            if event_id not in approved:
                continue
            if experimental:
                observation["quality_flags"]["experimental_event_local_gate"] = True
                observation["metrics"]["event_local_similarity_to_direction"] = gated.similarities[event_id]
            anchor = observations_by_id[anchor_id]
            # Identity routing uses the existing owned repository member.
            # Centroid uses ONLY the new event vector (not the old repo twice).
            members = (anchor_id, event_id)
            stable_id = hashlib.sha256("|".join(members).encode("utf-8")).hexdigest()[:20]
            clusters.append(Microcluster(
                cluster_id=f"history:{stable_id}",
                member_ids=members,
                centroid=tuple(float(value) for value in vector),
                member_count=2,
            ))
            observations_for_ingest[anchor_id] = anchor
            observations_for_ingest[event_id] = observation
            accepted_observations.append(observation)

        update: TrendStateUpdateResult | None = None
        if clusters:
            result = MicroclusteringResult(
                profile=state.profile,
                config=PROFILE_CONFIGS[state.profile],
                embedding_model=state.embedding_model,
                clusters=tuple(clusters),
                assignments={
                    member: cluster.cluster_id
                    for cluster in clusters
                    for member in cluster.member_ids
                },
            )
            # All historical clusters have a real already-owned repository anchor.
            # This prevents accidental creation of new trends during backfill.
            update = manager.ingest(
                result, observations_for_ingest,
                now=observed_at.isoformat().replace("+00:00", "Z"),
            )
            if update.created_trend_ids or any(a.trend_id != trend_id for a in update.assignments):
                raise RuntimeError("historical enrichment unexpectedly changed trend identity")

        return GitHubBridgeResult(
            trend_id=trend_id,
            checked_repositories=tuple(repo for _, repo in candidates),
            repositories_without_event=tuple(no_event),
            verified_event_ids=tuple(event_ids),
            accepted_event_ids=gated.accepted_ids,
            rejected_event_ids=gated.rejected_ids,
            similarities=gated.similarities,
            accepted_observations=tuple(accepted_observations),
            update=update,
            verified_observations=tuple(observation for _, observation in events),
        )


def _evidence_text(observation: Mapping[str, Any]) -> str:
    title = str(observation.get("title") or "").strip()
    body = str(observation.get("text") or "").strip()
    # Do not inject aliases/matched search terms: that would make the
    # semantic gate circular and boost an otherwise irrelevant commit.
    return " ".join(part for part in (title, body) if part).strip()
