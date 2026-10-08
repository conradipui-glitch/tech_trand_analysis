"""End-to-end B-034 pipeline test with mocked GitHub and deterministic embeddings."""
import unittest
from datetime import datetime, timezone

import httpx

from tech_trend_analysis.github_live_pipeline import run_github_pipeline
from tech_trend_analysis.source_router import SourceRouter
from tech_trend_analysis.sources.github import GitHubAdapter
from tech_trend_analysis.sources.github_history import GitHubHistoryClient


NOW = datetime(2026, 8, 29, tzinfo=timezone.utc)


def repo(full_name):
    return {
        "full_name": full_name,
        "name": full_name.rsplit("/", 1)[1],
        "html_url": f"https://github.com/{full_name}",
        "description": "retrieval augmented generation language model framework",
        "owner": {"login": full_name.split("/")[0], "id": 20},
        "topics": ["rag"],
        "language": "Python",
        "fork": False,
        "archived": False,
        "created_at": "2018-01-01T00:00:00Z",
        "updated_at": "2026-08-28T00:00:00Z",
    }


def handler(request):
    path = request.url.path
    if path == "/search/repositories":
        return httpx.Response(200, json={
            "items": [repo("huggingface/transformers"), repo("acme/rag-radio")],
        })
    if path == "/search/commits":
        is_good = "huggingface/transformers" in request.url.params.get("q", "")
        repository = "huggingface/transformers" if is_good else "acme/rag-radio"
        title = (
            "Add retrieval augmented generation language model retriever"
            if is_good else "RAG unrelated radio frequency broadcast feature"
        )
        return httpx.Response(200, json={"items": [{
            "sha": "commit123",
            "html_url": f"https://github.com/{repository}/commit/commit123",
            "commit": {
                "message": title,
                "committer": {"date": "2020-09-22T16:29:58Z" if is_good else "2020-01-01T00:00:00Z"},
            },
        }]})
    if path.endswith("/releases") or path.endswith("/tags"):
        return httpx.Response(200, json=[])
    raise AssertionError(f"unexpected request: {request.url}")


def embed(texts):
    return [
        [0.0, 1.0] if "radio" in txt.casefold() and "broadcast" in txt.casefold() else [1.0, 0.0]
        for txt in texts
    ]


class GitHubLivePipelineTests(unittest.TestCase):
    def test_end_to_end_real_client_adapters_mock_transport_no_backdating(self):
        router = SourceRouter.from_yaml("config/sources.yaml")
        transport = httpx.MockTransport(handler)
        with (
            GitHubAdapter(transport=transport, max_retries=0) as adapter,
            GitHubHistoryClient(transport=transport, max_retries=0) as history,
        ):
            output = run_github_pipeline(
                technology_direction="retrieval augmented generation",
                query_text="retrieval augmented generation",
                profile_override="software_ai",
                router=router,
                adapter=adapter,
                history_client=history,
                embed=embed,
                aliases=("retrieval augmented generation",),
                context_terms=("language model",),
                observed_at=NOW,
                max_discovery=2,
                max_history_repositories_per_cluster=2,
            )
        self.assertEqual("software_ai", output.profile)
        self.assertEqual(2, output.discovery_count)
        self.assertEqual(1, output.cluster_count)
        self.assertEqual(2, output.checked_repository_count)
        self.assertEqual(2, output.verified_event_count)
        self.assertEqual(1, output.accepted_event_count)
        self.assertEqual(1, output.rejected_event_count)
        self.assertEqual(3, len(output.observations))
        self.assertEqual(1, len(output.trend_states))
        state = output.trend_states[0]
        self.assertEqual("2020-09-22T16:29:58Z", state["first_seen"])
        self.assertEqual("2020-09-22T16:29:58Z", state["first_evidence_at"]["implementation"])
        self.assertNotIn("2018-01", state["periods"][0]["period"])
        self.assertEqual("detector_evidence_snapshot_not_top15", output.summary()["status"])

        raw_repos = [obs for obs in output.observations if obs["artifact_kind"] == "repository"]
        self.assertEqual(2, len(raw_repos))
        self.assertTrue(all(obs["published_at"] is None for obs in raw_repos))
        self.assertTrue(all(obs["metrics"]["repository_created_at"].startswith("2018") for obs in raw_repos))

    def test_empty_discovery_is_valid_not_fake_trends(self):
        router = SourceRouter.from_yaml("config/sources.yaml")
        with GitHubAdapter(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={"items": []})),
            max_retries=0,
        ) as adapter:
            output = run_github_pipeline(
                technology_direction="AI agents",
                query_text="AI agents",
                router=router,
                profile_override="software_ai",
                adapter=adapter,
                history_client=None,
                embed=lambda _: self.fail("must not call embed"),
                observed_at=NOW,
            )
        self.assertEqual(0, output.cluster_count)
        self.assertEqual((), output.trend_states)

    def test_disabled_source_rejected(self):
        router = SourceRouter.from_yaml("config/sources.yaml")
        with GitHubAdapter(
            transport=httpx.MockTransport(lambda _: self.fail("should not search"))
        ) as adapter:
            with self.assertRaisesRegex(ValueError, "disabled"):
                run_github_pipeline(
                    technology_direction="solid-state batteries",
                    query_text="solid-state batteries",
                    router=router,
                    profile_override="materials_energy",
                    adapter=adapter,
                    history_client=None,
                    embed=embed,
                    observed_at=NOW,
                )


if __name__ == "__main__":
    unittest.main()
