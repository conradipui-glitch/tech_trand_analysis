import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

import httpx
import jsonschema

from tech_trend_analysis.sources.github import GitHubAdapter, GitHubQuery


class GitHubAdapterTests(unittest.TestCase):
    def test_repository_created_at_is_metadata_not_published_at(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual("/search/repositories", request.url.path)
            return httpx.Response(
                200,
                json={
                    "total_count": 1,
                    "items": [_repo("vercel-labs/agent-browser")],
                },
            )

        query = GitHubQuery(
            technology_direction="AI agents",
            source_profile="software_ai",
            query_text='"AI agents" browser automation',
            query_id="query:ai-agents:test",
            per_page=10,
            max_pages=1,
        )
        observed_at = datetime(2026, 8, 30, 1, 0, tzinfo=timezone.utc)
        with GitHubAdapter(transport=httpx.MockTransport(handler), max_retries=0) as adapter:
            observations = adapter.collect(query, observed_at=observed_at)

        self.assertEqual(1, len(observations))
        observation = observations[0]
        self.assertIsNone(observation["published_at"])
        self.assertEqual("2026-08-30T01:00:00Z", observation["observed_at"])
        self.assertEqual("2024-01-02T03:04:05Z", observation["metrics"]["repository_created_at"])
        self.assertEqual("current_snapshot_only", observation["quality_flags"]["time_semantics"])
        self.assertFalse(observation["quality_flags"]["historical_timestamp_verified"])

        schema = json.loads(Path("schemas/observation.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(observation)

    def test_default_collection_filters_forks_and_archived_repositories(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={
                    "total_count": 3,
                    "items": [
                        _repo("org/live"),
                        _repo("org/fork", fork=True),
                        _repo("org/archived", archived=True),
                    ],
                },
            )

        query = GitHubQuery(
            technology_direction="AI agents",
            source_profile="software_ai",
            query_text="agent framework",
            query_id="q",
            per_page=10,
            max_pages=1,
        )
        with GitHubAdapter(transport=httpx.MockTransport(handler), max_retries=0) as adapter:
            candidates = list(adapter.iter_candidates(query))
        self.assertEqual(["org/live"], [candidate.full_name for candidate in candidates])

    def test_pagination_deduplicates_repository_full_name(self):
        def handler(request: httpx.Request) -> httpx.Response:
            page = request.url.params.get("page")
            if page == "1":
                return httpx.Response(
                    200,
                    json={"items": [_repo("org/a"), _repo("org/b")]},
                )
            if page == "2":
                return httpx.Response(
                    200,
                    json={"items": [_repo("org/b"), _repo("org/c")]},
                )
            raise AssertionError(f"unexpected page {page}")

        query = GitHubQuery(
            technology_direction="agent frameworks",
            source_profile="software_ai",
            query_text="agent framework",
            query_id="q",
            per_page=2,
            max_pages=2,
        )
        with GitHubAdapter(transport=httpx.MockTransport(handler), max_retries=0) as adapter:
            candidates = list(adapter.iter_candidates(query))
        self.assertEqual(["org/a", "org/b", "org/c"], [candidate.full_name for candidate in candidates])


def _repo(full_name: str, *, fork: bool = False, archived: bool = False) -> dict:
    owner, name = full_name.split("/", 1)
    return {
        "full_name": full_name,
        "name": name,
        "html_url": f"https://github.com/{full_name}",
        "description": "Browser automation framework for AI agents",
        "owner": {"login": owner, "id": 123},
        "topics": ["ai-agents", "browser-automation"],
        "language": "TypeScript",
        "license": {"spdx_id": "Apache-2.0"},
        "stargazers_count": 100,
        "forks_count": 5,
        "open_issues_count": 2,
        "watchers_count": 100,
        "size": 2048,
        "created_at": "2024-01-02T03:04:05Z",
        "updated_at": "2026-08-29T20:00:00Z",
        "pushed_at": "2026-08-29T19:00:00Z",
        "archived": archived,
        "fork": fork,
    }


if __name__ == "__main__":
    unittest.main()
