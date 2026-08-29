import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jsonschema

from tech_trend_analysis.sources.github_history import GitHubHistoryClient, GitHubHistoryQuery


class GitHubHistoryTests(unittest.TestCase):
    def test_earliest_relevant_commit_beats_later_release(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/search/commits":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "sha": "later",
                                "html_url": "https://github.com/microsoft/LoRA/commit/later",
                                "commit": {
                                    "message": "LoRA cleanup",
                                    "committer": {"date": "2022-01-05T00:00:00Z"},
                                },
                            },
                            {
                                "sha": "first",
                                "html_url": "https://github.com/microsoft/LoRA/commit/first",
                                "commit": {
                                    "message": "applied LoRA to DeBERTa and RoBERTa",
                                    "committer": {"date": "2021-09-20T03:35:47Z"},
                                },
                            },
                        ]
                    },
                )
            if request.url.path == "/repos/microsoft/LoRA/releases":
                return httpx.Response(
                    200,
                    json=[
                        {
                            "id": 7,
                            "name": "LoRA v1",
                            "tag_name": "v1",
                            "body": "LoRA adapters",
                            "published_at": "2022-02-01T00:00:00Z",
                            "html_url": "https://github.com/microsoft/LoRA/releases/tag/v1",
                            "draft": False,
                        }
                    ],
                )
            if request.url.path == "/repos/microsoft/LoRA/tags":
                return httpx.Response(200, json=[])
            raise AssertionError(f"unexpected request: {request.url}")

        query = GitHubHistoryQuery(
            repository="microsoft/LoRA",
            technology_direction="low-rank adaptation of large language models",
            source_profile="software_ai",
            aliases=("low rank adaptation", "lora"),
            context_terms=("language model", "adapter", "transformer"),
            distinctive_terms=("LoRA",),
            query_id="validation:lora",
        )
        with GitHubHistoryClient(transport=httpx.MockTransport(handler), max_retries=0) as client:
            event = client.verify_earliest(query)

        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual("commit", event.event_kind)
        self.assertEqual("first", event.external_id)
        self.assertEqual("2021-09-20T03:35:47Z", event.occurred_at)
        self.assertIn("LoRA", event.matched_terms)

    def test_mixed_case_distinctive_term_rejects_lora_radio_spelling(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/search/commits":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "sha": "radio",
                                "html_url": "https://github.com/example/project/commit/radio",
                                "commit": {
                                    "message": "LoRa wireless sensor network update",
                                    "committer": {"date": "2020-01-01T00:00:00Z"},
                                },
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/releases") or request.url.path.endswith("/tags"):
                return httpx.Response(200, json=[])
            raise AssertionError(f"unexpected request: {request.url}")

        query = GitHubHistoryQuery(
            repository="example/project",
            technology_direction="low-rank adaptation",
            source_profile="software_ai",
            aliases=("lora",),
            context_terms=("llm", "language model", "adapter"),
            distinctive_terms=("LoRA",),
        )
        with GitHubHistoryClient(transport=httpx.MockTransport(handler), max_retries=0) as client:
            self.assertIsNone(client.verify_earliest(query))

    def test_observation_uses_event_timestamp_and_validates_schema(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/search/commits":
                return httpx.Response(
                    200,
                    json={
                        "items": [
                            {
                                "sha": "ragcommit",
                                "html_url": "https://github.com/huggingface/transformers/commit/ragcommit",
                                "commit": {
                                    "message": "RAG integration with RagRetriever and retrieval tests",
                                    "committer": {"date": "2020-09-22T16:29:58Z"},
                                },
                            }
                        ]
                    },
                )
            if request.url.path.endswith("/releases") or request.url.path.endswith("/tags"):
                return httpx.Response(200, json=[])
            raise AssertionError(f"unexpected request: {request.url}")

        query = GitHubHistoryQuery(
            repository="huggingface/transformers",
            technology_direction="retrieval-augmented generation",
            source_profile="software_ai",
            aliases=("retrieval augmented generation", "rag"),
            context_terms=("retrieval", "language model"),
            distinctive_terms=("RagRetriever",),
            query_id="validation:rag",
        )
        with GitHubHistoryClient(transport=httpx.MockTransport(handler), max_retries=0) as client:
            event = client.verify_earliest(query)
        assert event is not None
        observation = event.to_observation(
            query,
            observed_at=datetime(2026, 8, 30, tzinfo=timezone.utc),
        )

        schema = json.loads(Path("schemas/observation.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(observation)
        self.assertEqual("implementation", observation["evidence_type"])
        self.assertEqual("2020-09-22T16:29:58Z", observation["published_at"])
        self.assertTrue(observation["quality_flags"]["historical_timestamp_verified"])
        self.assertFalse(observation["quality_flags"]["mutable_repository_metadata_used_for_timestamp"])


if __name__ == "__main__":
    unittest.main()
