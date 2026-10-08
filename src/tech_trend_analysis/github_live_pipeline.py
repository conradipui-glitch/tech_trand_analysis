"""Bounded, opt-in local pipeline: GitHub discovery -> clusters -> verified history.

This is a local/VPS runner, not a Cloudflare Worker or a TOP-15 claim.
Only observations backed by dated Git events may move historical boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from typing import Any, Callable, Sequence

import numpy as np

from .clustering import Microclusterer
from .github_history_bridge import GitHubBridgePolicy, GitHubHistoryBridge
from .source_router import SourceRouter
from .sources.github import GitHubAdapter, GitHubQuery
from .sources.github_history import GitHubHistoryClient
from .trend_state import TrendStateManager


EmbeddingFn = Callable[[Sequence[str]], Sequence[Sequence[float]]]


@dataclass(frozen=True, slots=True)
class GitHubPipelineOutput:
    technology_direction: str
    profile: str
    discovery_count: int
    cluster_count: int
    checked_repository_count: int
    verified_event_count: int
    accepted_event_count: int
    rejected_event_count: int
    observations: tuple[dict[str, Any], ...]
    trend_states: tuple[dict[str, Any], ...]

    def summary(self) -> dict[str, Any]:
        return {
            "technology_direction": self.technology_direction,
            "profile": self.profile,
            "discovery_count": self.discovery_count,
            "cluster_count": self.cluster_count,
            "checked_repository_count": self.checked_repository_count,
            "verified_event_count": self.verified_event_count,
            "accepted_event_count": self.accepted_event_count,
            "rejected_event_count": self.rejected_event_count,
            "status": "detector_evidence_snapshot_not_top15",
            "historical_policy": "verified_git_event_and_semantic_gate_only",
            "trends": [
                {
                    "trend_id": state["trend_id"],
                    "observation_count": state["observation_count"],
                    "first_seen": state["first_seen"],
                    "first_evidence_at": state["first_evidence_at"],
                    "evidence_counts": state["evidence_counts"],
                }
                for state in self.trend_states
            ],
        }


def run_github_pipeline(
    *,
    technology_direction: str,
    query_text: str,
    router: SourceRouter,
    adapter: GitHubAdapter,
    history_client: GitHubHistoryClient,
    embed: EmbeddingFn,
    embedding_model: str = "BAAI/bge-m3",
    aliases: Sequence[str] = (),
    context_terms: Sequence[str] = (),
    distinctive_terms: Sequence[str] = (),
    max_discovery: int = 20,
    repository_sort: str = "updated",
    max_history_repositories_per_cluster: int = 3,
    history_similarity_threshold: float = 0.82,
    observed_at: datetime | None = None,
    profile_override: str | None = None,
) -> GitHubPipelineOutput:
    if max_discovery < 1:
        raise ValueError("max_discovery must be >= 1")
    if max_history_repositories_per_cluster < 1:
        raise ValueError("max_history_repositories_per_cluster must be >= 1")
    clock = observed_at or datetime.now(timezone.utc)
    if clock.tzinfo is None:
        raise ValueError("observed_at must be timezone-aware")
    clock = clock.astimezone(timezone.utc)

    route = router.route(technology_direction, profile_override=profile_override)
    policy = next((item for item in route.providers if item.provider == "github"), None)
    if policy is None or not policy.enabled:
        raise ValueError(f"GitHub discovery disabled for profile {route.profile}")

    phrases = tuple(aliases) if aliases else (technology_direction.strip(),)
    query = GitHubQuery(
        technology_direction=technology_direction.strip(),
        source_profile=route.profile,
        query_text=query_text.strip(),
        query_id=f"live-github:{clock.strftime('%Y%m%dT%H%M%SZ')}",
        per_page=min(100, max_discovery),
        sort=repository_sort,
        max_pages=1,
    )
    discovered = [
        adapter.to_observation(candidate, query, observed_at=clock)
        for candidate in islice(adapter.iter_candidates(query), max_discovery)
    ]
    if not discovered:
        return GitHubPipelineOutput(
            technology_direction, route.profile, 0, 0, 0, 0, 0, 0, (), ()
        )

    ids = [obs["observation_id"] for obs in discovered]
    texts = [" ".join(filter(None, (obs["title"], obs.get("text")))) for obs in discovered]
    vectors = np.asarray(embed(texts), dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(discovered) or not np.isfinite(vectors).all():
        raise ValueError("discovery embedder returned invalid vectors")

    clustering = Microclusterer(embedding_model=embedding_model).cluster(
        profile=route.profile, observation_ids=ids, texts=texts, vectors=vectors
    )
    manager = TrendStateManager()
    by_id = {obs["observation_id"]: obs for obs in discovered}
    manager.ingest(clustering, by_id, now=clock.isoformat().replace("+00:00", "Z"))

    bridge = GitHubHistoryBridge(
        history_client=history_client,
        embed=embed,
        embedding_model=embedding_model,
        policy=GitHubBridgePolicy(
            max_repositories_per_trend=max_history_repositories_per_cluster,
            similarity_threshold=history_similarity_threshold,
        ),
    )
    checked = verified = accepted = rejected = 0
    # Historical verification depends on already formed, persistent trend identity.
    for trend_id in sorted(manager.states):
        result = bridge.enrich(
            manager=manager,
            trend_id=trend_id,
            observations_by_id=by_id,
            aliases=phrases,
            context_terms=context_terms,
            distinctive_terms=distinctive_terms,
            now=clock,
        )
        checked += len(result.checked_repositories)
        verified += len(result.verified_event_ids)
        accepted += len(result.accepted_event_ids)
        rejected += len(result.rejected_event_ids)
        for observation in result.accepted_observations:
            by_id[observation["observation_id"]] = observation

    return GitHubPipelineOutput(
        technology_direction=technology_direction,
        profile=route.profile,
        discovery_count=len(discovered),
        cluster_count=len(clustering.clusters),
        checked_repository_count=checked,
        verified_event_count=verified,
        accepted_event_count=accepted,
        rejected_event_count=rejected,
        observations=tuple(by_id[key] for key in sorted(by_id)),
        trend_states=tuple(manager.states[key].to_dict() for key in sorted(manager.states)),
    )
