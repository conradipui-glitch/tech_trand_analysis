import unittest

import numpy as np

from tech_trend_analysis.clustering import (
    Microcluster,
    MicroclusterConfig,
    MicroclusteringResult,
)
from tech_trend_analysis.trend_state import (
    TrendStateConflictError,
    TrendStateManager,
)


CONFIG = MicroclusterConfig(
    algorithm="agglomerative_average_cosine",
    distance_threshold=0.4,
    calibration="test",
)


def observation(
    observation_id: str,
    *,
    evidence_type: str,
    provider: str,
    artifact_kind: str,
    published_at: str,
    actor: str,
    direction: str = "neuromorphic computing",
):
    return {
        "observation_id": observation_id,
        "provider": provider,
        "evidence_type": evidence_type,
        "artifact_kind": artifact_kind,
        "published_at": published_at,
        "observed_at": "2026-08-29T18:00:00Z",
        "actors": [
            {
                "name": actor,
                "kind": "organization",
                "external_id": actor.lower().replace(" ", "-"),
                "country": None,
            }
        ],
        "collection_context": {
            "technology_direction": direction,
            "source_profile": "hardware_semiconductor",
        },
    }


def result(*clusters: Microcluster) -> MicroclusteringResult:
    assignments = {
        observation_id: cluster.cluster_id
        for cluster in clusters
        for observation_id in cluster.member_ids
    }
    return MicroclusteringResult(
        profile="hardware_semiconductor",
        config=CONFIG,
        embedding_model="BAAI/bge-m3",
        clusters=tuple(clusters),
        assignments=assignments,
    )


class TrendStateManagerTests(unittest.TestCase):
    def test_creates_state_with_temporal_and_diversity_counters(self):
        manager = TrendStateManager(match_similarity_threshold=0.90)
        observations = {
            "paper-1": observation(
                "paper-1",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-15",
                actor="Lab A",
            ),
            "patent-1": observation(
                "patent-1",
                evidence_type="patent",
                provider="epo_ops",
                artifact_kind="patent",
                published_at="2026-02-20",
                actor="Company B",
            ),
        }
        cluster = Microcluster(
            cluster_id="micro:first",
            member_ids=("paper-1", "patent-1"),
            centroid=(1.0, 0.0),
            member_count=2,
        )

        update = manager.ingest(
            result(cluster),
            observations,
            now="2026-03-01T00:00:00Z",
        )

        self.assertEqual(1, len(update.created_trend_ids))
        state = manager.states[update.created_trend_ids[0]]
        self.assertEqual(2, state.observation_count)
        self.assertEqual({"research": 1, "patent": 1}, state.evidence_counts)
        self.assertEqual({"openalex": 1, "epo_ops": 1}, state.provider_counts)
        self.assertEqual(2, state.evidence_diversity)
        self.assertEqual(2, state.provider_diversity)
        self.assertEqual(2, state.actor_diversity)
        self.assertEqual("2026-01-15T00:00:00Z", state.first_seen)
        self.assertEqual("2026-02-20T00:00:00Z", state.last_seen)
        self.assertEqual("2026-01-15T00:00:00Z", state.first_evidence_at["research"])
        self.assertEqual("2026-02-20T00:00:00Z", state.first_evidence_at["patent"])
        self.assertEqual(1, state.periods["2026-01"].total)
        self.assertEqual(1, state.periods["2026-02"].total)

    def test_rolling_recollection_is_idempotent(self):
        manager = TrendStateManager(match_similarity_threshold=0.90)
        observations = {
            "paper-1": observation(
                "paper-1",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-15",
                actor="Lab A",
            )
        }
        first = Microcluster(
            cluster_id="micro:first",
            member_ids=("paper-1",),
            centroid=(1.0, 0.0),
            member_count=1,
        )
        first_update = manager.ingest(result(first), observations)
        trend_id = first_update.created_trend_ids[0]

        replay = Microcluster(
            cluster_id="micro:replayed-window",
            member_ids=("paper-1",),
            centroid=(0.99, 0.01),
            member_count=1,
        )
        second_update = manager.ingest(result(replay), observations)

        self.assertEqual(trend_id, second_update.assignments[0].trend_id)
        self.assertEqual("existing_observation", second_update.assignments[0].reason)
        self.assertEqual(0, second_update.assignments[0].new_observation_count)
        self.assertEqual(1, manager.states[trend_id].observation_count)
        self.assertEqual({"research": 1}, manager.states[trend_id].evidence_counts)

    def test_centroid_match_extends_existing_trend_and_records_transition(self):
        manager = TrendStateManager(match_similarity_threshold=0.90)
        first_observations = {
            "paper-1": observation(
                "paper-1",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-15",
                actor="Lab A",
            )
        }
        first_cluster = Microcluster(
            cluster_id="micro:first",
            member_ids=("paper-1",),
            centroid=(1.0, 0.0),
            member_count=1,
        )
        first_update = manager.ingest(result(first_cluster), first_observations)
        trend_id = first_update.created_trend_ids[0]

        second_observations = {
            "repo-1": observation(
                "repo-1",
                evidence_type="implementation",
                provider="github",
                artifact_kind="repository",
                published_at="2026-03-10",
                actor="Company B",
            )
        }
        second_cluster = Microcluster(
            cluster_id="micro:later",
            member_ids=("repo-1",),
            centroid=(0.995, 0.1),
            member_count=1,
        )
        update = manager.ingest(result(second_cluster), second_observations)

        self.assertEqual(trend_id, update.assignments[0].trend_id)
        self.assertEqual("centroid", update.assignments[0].reason)
        self.assertGreater(update.assignments[0].similarity, 0.99)
        state = manager.states[trend_id]
        self.assertEqual(2, state.observation_count)
        self.assertEqual({"research": 1, "implementation": 1}, state.evidence_counts)
        self.assertEqual("2026-03-10T00:00:00Z", state.first_evidence_at["implementation"])
        self.assertAlmostEqual(1.0, float(np.linalg.norm(np.asarray(state.centroid))), places=6)

    def test_low_similarity_creates_distinct_trend(self):
        manager = TrendStateManager(match_similarity_threshold=0.90)
        observations_a = {
            "a": observation(
                "a",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-01",
                actor="Lab A",
            )
        }
        manager.ingest(
            result(Microcluster("micro:a", ("a",), (1.0, 0.0), 1)),
            observations_a,
        )

        observations_b = {
            "b": observation(
                "b",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-02-01",
                actor="Lab B",
            )
        }
        update = manager.ingest(
            result(Microcluster("micro:b", ("b",), (0.0, 1.0), 1)),
            observations_b,
        )

        self.assertEqual(1, len(update.created_trend_ids))
        self.assertEqual(2, len(manager.states))
        self.assertEqual("new", update.assignments[0].reason)

    def test_fails_closed_when_microcluster_bridges_two_existing_trends(self):
        manager = TrendStateManager(match_similarity_threshold=0.95)
        observations = {
            "a": observation(
                "a",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-01",
                actor="Lab A",
            ),
            "b": observation(
                "b",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-02",
                actor="Lab B",
            ),
        }
        manager.ingest(
            result(
                Microcluster("micro:a", ("a",), (1.0, 0.0), 1),
                Microcluster("micro:b", ("b",), (0.0, 1.0), 1),
            ),
            observations,
        )
        self.assertEqual(2, len(manager.states))

        bridge = Microcluster(
            cluster_id="micro:bridge",
            member_ids=("a", "b"),
            centroid=(0.707, 0.707),
            member_count=2,
        )
        with self.assertRaises(TrendStateConflictError):
            manager.ingest(result(bridge), observations)

    def test_direction_boundary_prevents_cross_query_merge(self):
        manager = TrendStateManager(match_similarity_threshold=0.50)
        first = {
            "a": observation(
                "a",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-01-01",
                actor="Lab A",
                direction="neuromorphic computing",
            )
        }
        manager.ingest(
            result(Microcluster("micro:a", ("a",), (1.0, 0.0), 1)),
            first,
        )

        second = {
            "b": observation(
                "b",
                evidence_type="research",
                provider="openalex",
                artifact_kind="paper",
                published_at="2026-02-01",
                actor="Lab B",
                direction="photonic computing",
            )
        }
        update = manager.ingest(
            result(Microcluster("micro:b", ("b",), (1.0, 0.0), 1)),
            second,
        )
        self.assertEqual(1, len(update.created_trend_ids))
        self.assertEqual(2, len(manager.states))


if __name__ == "__main__":
    unittest.main()
