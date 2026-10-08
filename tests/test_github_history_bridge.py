"""B-034 integration tests: discovery ownership -> event history -> semantic gate -> TrendState."""
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from tech_trend_analysis.clustering import Microcluster, MicroclusterConfig, MicroclusteringResult
from tech_trend_analysis.github_history_bridge import GitHubBridgePolicy, GitHubHistoryBridge
from tech_trend_analysis.sources.github_history import VerifiedGitEvent
from tech_trend_analysis.trend_state import TrendStateManager


NOW = datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc)
CONFIG = MicroclusterConfig("agglomerative_average_cosine", 0.4, calibration="test")
MODEL = "BAAI/bge-m3"
DIRECTION = "low-rank adaptation of language models"


def observation(oid, typ, kind, when, repo=None):
    is_repo = kind == "repository"
    name = repo.split("/")[1] if repo else kind
    return {
        "schema_version": "0.2.0",
        "observation_id": oid,
        "provider": "github" if is_repo else "openalex",
        "evidence_type": typ,
        "artifact_kind": kind,
        "external_id": repo or oid,
        "canonical_url": f"https://github.com/{repo}" if repo else "https://openalex.org/W123",
        "title": name,
        "text": "LoRA language model adapters",
        "published_at": None if is_repo else when,
        "updated_at": None,
        "observed_at": NOW.isoformat().replace("+00:00", "Z"),
        "language": "en",
        "actors": [],
        "source_topics": [],
        "classifications": [],
        "metrics": {"repository_created_at": "2015-01-01T00:00:00Z"} if is_repo else {},
        "relationships": [],
        "quality_flags": {"historical_timestamp_verified": False} if is_repo else {},
        "fingerprints": {"canonical_key": oid},
        "collection_context": {
            "technology_direction": DIRECTION,
            "source_profile": "software_ai",
            "query_id": "fixture",
            "matched_terms": ["LoRA"],
        },
        "rights": {"license": None, "access_level": "public"},
        "analysis": {},
        "raw_ref": None,
        "provenance": {"collector": "test", "collector_version": "0.1"},
    }


def prepared():
    manager = TrendStateManager()
    repo = "microsoft/LoRA"
    paper = observation("openalex:paper-1", "research", "paper", "2021-06-17T00:00:00Z")
    repository = observation(f"github:{repo}", "implementation", "repository", None, repo)
    observations = {o["observation_id"]: o for o in (paper, repository)}
    ids = tuple(observations)
    cluster = Microcluster("initial:lora", ids, (1.0, 0.0), len(ids))
    batch = MicroclusteringResult(
        "software_ai", CONFIG, MODEL, (cluster,), {oid: cluster.cluster_id for oid in ids}
    )
    updated = manager.ingest(batch, observations, now="2026-08-29T22:00:00Z")
    return manager, updated.created_trend_ids[0], observations


class StubHistory:
    def __init__(self, event):
        self.event = event
        self.queries = []

    def verify_earliest(self, query):
        self.queries.append(query)
        return self.event


def event(kind="commit", when="2021-09-16T21:48:51Z", repo="microsoft/LoRA"):
    return VerifiedGitEvent(
        repository=repo,
        event_kind=kind,
        external_id="abcdef123456",
        occurred_at=when,
        title="Add LoRA adapters",
        evidence_text="Add LoRA adapters to large language model fine tuning",
        url=f"https://github.com/{repo}/commit/abcdef123456",
        matched_terms=("LoRA", "adapter"),
        source_endpoint="GET /search/commits",
    )


class GitHubHistoryBridgeTests(unittest.TestCase):
    def make_bridge(self, history=None, embedding=None, model=MODEL):
        return GitHubHistoryBridge(
            history_client=history if history is not None else StubHistory(event()),
            embed=embedding or (lambda texts: [[1.0, 0.0] for _ in texts]),
            embedding_model=model,
            policy=GitHubBridgePolicy(max_repositories_per_trend=3, similarity_threshold=0.82),
        )

    def test_timestamped_event_passes_and_updates_existing_trend_without_new_identity(self):
        manager, trend_id, observations = prepared()
        bridge = self.make_bridge()
        output = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("low rank adaptation", "lora"),
            context_terms=("language model", "adapter"),
            distinctive_terms=("LoRA",),
            now=NOW,
        )
        self.assertEqual(1, len(output.accepted_event_ids))
        self.assertEqual((), output.rejected_event_ids)
        self.assertEqual((), output.repositories_without_event)
        self.assertEqual(1, len(output.update.assignments))
        self.assertEqual((), output.update.created_trend_ids)
        self.assertEqual(trend_id, output.update.assignments[0].trend_id)
        state = manager.states[trend_id]
        self.assertEqual("2021-06-17T00:00:00Z", state.first_seen)
        self.assertEqual("2021-09-16T21:48:51Z", state.first_evidence_at["implementation"])
        self.assertEqual(3, state.observation_count)
        self.assertEqual("2026-08", state.periods["2026-08"].period)
        self.assertEqual(1, state.periods["2021-09"].total)
        self.assertEqual(1, len(manager.states))
        self.assertEqual("microsoft/LoRA", bridge.history_client.queries[0].repository)
        self.assertEqual("LoRA", bridge.history_client.queries[0].distinctive_terms[0])
        schema = json.loads(Path("schemas/observation.schema.json").read_text())
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(
            output.accepted_observations[0]
        )

        # Replay must not recount the same evidence or increment update_count.
        old_count = state.observation_count
        old_updates = state.update_count
        again = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("lora",), distinctive_terms=("LoRA",), now=NOW,
        )
        self.assertEqual(0, again.update.assignments[0].new_observation_count)
        self.assertEqual(old_count, state.observation_count)
        self.assertEqual(old_updates, state.update_count)

    def test_low_similarity_event_rejected_before_any_state_mutation(self):
        manager, trend_id, observations = prepared()
        state = manager.states[trend_id]
        before = state.to_dict()
        bridge = self.make_bridge(embedding=lambda _: [[0.0, 1.0]])
        output = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("lora",), distinctive_terms=("LoRA",), now=NOW,
        )
        self.assertEqual((), output.accepted_event_ids)
        self.assertEqual(1, len(output.rejected_event_ids))
        self.assertIsNone(output.update)
        self.assertEqual(before, state.to_dict())

    def test_no_event_is_not_made_up_from_repository_created_at(self):
        manager, trend_id, observations = prepared()
        state = manager.states[trend_id]
        before = state.to_dict()
        bridge = self.make_bridge(history=StubHistory(None), embedding=lambda _: self.fail("embed called"))
        output = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("lora",), now=NOW,
        )
        self.assertEqual(("microsoft/LoRA",), output.repositories_without_event)
        self.assertEqual((), output.verified_event_ids)
        self.assertEqual(before, state.to_dict())

    def test_fails_closed_on_embedding_model_mismatch(self):
        manager, trend_id, observations = prepared()
        bridge = self.make_bridge(model="different/model")
        with self.assertRaisesRegex(ValueError, "embedding_model"):
            bridge.enrich(
                manager=manager, trend_id=trend_id, observations_by_id=observations,
                aliases=("lora",), now=NOW,
            )

    def test_fails_closed_on_bad_vector_shape_and_future_event(self):
        manager, trend_id, observations = prepared()
        bad_vector = self.make_bridge(embedding=lambda _: [[1.0, 0.0, 0.0]])
        with self.assertRaisesRegex(ValueError, "invalid shape"):
            bad_vector.enrich(
                manager=manager, trend_id=trend_id, observations_by_id=observations,
                aliases=("lora",), now=NOW,
            )
        future = self.make_bridge(history=StubHistory(event(when="2027-01-01T00:00:00Z")))
        with self.assertRaisesRegex(ValueError, "future"):
            future.enrich(
                manager=manager, trend_id=trend_id, observations_by_id=observations,
                aliases=("lora",), now=NOW,
            )
        self.assertEqual(2, manager.states[trend_id].observation_count)

    def test_experimental_event_local_gate_accepts_explicit_lora_adapter(self):
        manager, trend_id, observations = prepared()
        bridge = GitHubHistoryBridge(
            history_client=StubHistory(event()),
            embed=lambda texts: [[1.0, 0.0] for _ in texts],
            embedding_model=MODEL,
            policy=GitHubBridgePolicy(experimental_event_local_threshold=0.425),
        )
        result = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("lora",), distinctive_terms=("LoRA",), now=NOW,
        )
        self.assertEqual(1, len(result.accepted_event_ids))
        self.assertTrue(result.accepted_observations[0]["quality_flags"]["experimental_event_local_gate"])
        self.assertEqual(3, manager.states[trend_id].observation_count)

    def test_experimental_event_local_gate_rejects_lora_radio_even_with_high_cosine(self):
        manager, trend_id, observations = prepared()
        radio_event = VerifiedGitEvent(
            repository="microsoft/LoRA",
            event_kind="commit",
            external_id="radio123",
            occurred_at="2020-01-01T00:00:00Z",
            title="Add LoRa wireless sensor gateway",
            evidence_text="Add LoRa wireless sensor network radio gateway support",
            url="https://github.com/microsoft/LoRA/commit/radio123",
            matched_terms=("lora",),
            source_endpoint="GET /search/commits",
        )
        bridge = GitHubHistoryBridge(
            history_client=StubHistory(radio_event),
            embed=lambda texts: [[1.0, 0.0] for _ in texts],
            embedding_model=MODEL,
            policy=GitHubBridgePolicy(experimental_event_local_threshold=0.425),
        )
        before = manager.states[trend_id].to_dict()
        result = bridge.enrich(
            manager=manager, trend_id=trend_id, observations_by_id=observations,
            aliases=("lora",), distinctive_terms=("LoRA",), now=NOW,
        )
        self.assertEqual((), result.accepted_event_ids)
        self.assertEqual(1, len(result.rejected_event_ids))
        self.assertEqual(before, manager.states[trend_id].to_dict())

    def test_aliases_required_and_cross_trend_ownership_fails_closed(self):
        manager, trend_id, observations = prepared()
        bridge = self.make_bridge()
        with self.assertRaisesRegex(ValueError, "cluster-specific"):
            bridge.enrich(
                manager=manager, trend_id=trend_id, observations_by_id=observations,
                aliases=(), now=NOW,
            )
        manager.observation_to_trend["github:microsoft/LoRA"] = "trend:other"
        with self.assertRaisesRegex(ValueError, "not owned"):
            bridge.enrich(
                manager=manager, trend_id=trend_id, observations_by_id=observations,
                aliases=("lora",), now=NOW,
            )


if __name__ == "__main__":
    unittest.main()
