import tempfile
import unittest
from pathlib import Path

from tech_trend_analysis.storage.observations import (
    MemoryObservationStore,
    SqliteObservationStore,
)


def sample_observation(observation_id: str, direction: str, *, title: str = "Test"):
    return {
        "schema_version": "0.2.0",
        "observation_id": observation_id,
        "provider": "openalex",
        "evidence_type": "research",
        "artifact_kind": "paper",
        "external_id": observation_id.split(":", 1)[-1],
        "canonical_url": None,
        "title": title,
        "text": "Example evidence.",
        "published_at": "2026-08-20T00:00:00Z",
        "updated_at": None,
        "observed_at": "2026-08-29T17:00:00Z",
        "language": "en",
        "actors": [],
        "source_topics": [],
        "classifications": [],
        "metrics": {},
        "relationships": [],
        "quality_flags": {},
        "fingerprints": {
            "canonical_key": observation_id,
            "content_hash": None,
            "simhash": None,
        },
        "collection_context": {
            "technology_direction": direction,
            "source_profile": "mixed",
            "query_id": "q1",
            "matched_terms": [direction],
        },
        "analysis": {
            "relevance": None,
            "novelty": None,
            "cluster_id": None,
            "embedding_ref": None,
            "technology_labels": [],
        },
        "raw_ref": "file:///tmp/raw.jsonl.gz",
        "provenance": {
            "collector": "test",
            "collector_version": "0.1.0",
            "request_id": None,
            "source_endpoint": None,
        },
    }


class ObservationStoreContractMixin:
    async def make_store(self):
        raise NotImplementedError

    async def test_insert_get_update_and_filter(self):
        store = await self.make_store()
        first = sample_observation("openalex:W1", "neuromorphic computing")
        second = sample_observation("openalex:W2", "solid-state batteries")

        stats = await store.upsert_many([first, second])
        self.assertEqual(2, stats.inserted)
        self.assertEqual(0, stats.updated)

        loaded = await store.get("openalex:W1")
        self.assertEqual("Test", loaded["title"])

        changed = sample_observation(
            "openalex:W1",
            "neuromorphic computing",
            title="Updated title",
        )
        stats = await store.upsert_many([changed])
        self.assertEqual(0, stats.inserted)
        self.assertEqual(1, stats.updated)
        self.assertEqual("Updated title", (await store.get("openalex:W1"))["title"])

        filtered = await store.list_observations(
            technology_direction="neuromorphic computing"
        )
        self.assertEqual(["openalex:W1"], [item["observation_id"] for item in filtered])


class MemoryObservationStoreTests(
    ObservationStoreContractMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def make_store(self):
        return MemoryObservationStore()


class SqliteObservationStoreTests(
    ObservationStoreContractMixin,
    unittest.IsolatedAsyncioTestCase,
):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()

    async def asyncTearDown(self):
        self.tempdir.cleanup()

    async def make_store(self):
        return SqliteObservationStore(Path(self.tempdir.name) / "observations.sqlite3")


if __name__ == "__main__":
    unittest.main()
