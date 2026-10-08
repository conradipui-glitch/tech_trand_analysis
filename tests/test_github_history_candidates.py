"""B-040: chronological search pool and source-diff-backed implementation evidence."""
import unittest
from datetime import datetime, timezone

import httpx

from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.sources.github_history import (
    GitHubHistoryClient, GitHubHistoryQuery, VerifiedGitEvent,
)
from tech_trend_analysis.github_history_bridge import GitHubHistoryBridge, GitHubBridgePolicy
from test_github_history_bridge import prepared, MODEL


DATE = datetime(2026, 10, 9, tzinfo=timezone.utc)
QUERY = GitHubHistoryQuery(
    repository="huggingface/peft",
    technology_direction="low-rank adaptation of large language models",
    source_profile="software_ai",
    aliases=("lora",),
    distinctive_terms=("LoRA",),
    context_terms=("llm", "adapter"),
)


def commit(sha, date, message):
    return {
        "sha": sha, "html_url": f"https://github.com/huggingface/peft/commit/{sha}",
        "commit": {"message": message, "committer": {"date": date}},
    }


def event(repo, name, date, message):
    return VerifiedGitEvent(
        repository=repo, event_kind="commit", external_id=name,
        occurred_at=date, title=message.splitlines()[0],
        url=f"https://github.com/{repo}/commit/{name}",
        matched_terms=("lora",), source_endpoint="GET /search/commits",
        evidence_text=message,
    )


class MultiEventApiTests(unittest.TestCase):
    def test_recall_finds_earlier_lowercase_lora_and_same_sha_patch(self):
        requests = []
        def handler(request):
            requests.append(str(request.url))
            if request.url.path == "/search/commits":
                if request.url.params.get("page", "1") == "2":
                    return httpx.Response(200, json={"items": []})
                # Sorted by event time within API, plus duplicate across
                # query aliases that must be removed before selection.
                return httpx.Response(200, json={"items": [
                    commit("radio", "2020-03-01T00:00:00Z", "Add LoRa wireless radio gateway"),
                    commit("early", "2022-11-30T09:21:26Z", "add lora support"),
                    commit("later", "2023-02-01T10:11:35Z", "add LoRA modules_to_save to LoraConfig"),
                ]})
            if request.url.path.endswith("/releases") or request.url.path.endswith("/tags"):
                return httpx.Response(200, json=[])
            if request.url.path.endswith("/commits/early"):
                return httpx.Response(200, json={"files": [
                    {"filename": "src/pet/tuners/lora.py", "patch":
                     "@@ -1,3 +1,7 @@\n+from loralib import mark_only_lora_as_trainable\n+class LoRAConfig:\n+  LoRAModel = LoRAModel"},
                    {"filename": "README.md", "patch": "+ LoRA described in readme"}
                ]})
            if request.url.path.endswith("/commits/radio"):
                return httpx.Response(200, json={"files": [
                    {"filename": "radio.cpp", "patch": "+// LoRa radio gateway comment"}]})
            if request.url.path.endswith("/commits/later"):
                return httpx.Response(200, json={"files": []})
            raise AssertionError(str(request.url))
        with GitHubHistoryClient(transport=httpx.MockTransport(handler), max_retries=0) as client:
            candidates = client.candidate_events(QUERY, max_candidates=12,
                commit_pages_per_term=2, max_diff_checks=4)
        self.assertEqual(["radio", "early", "later"], [e.external_id for e in candidates])
        self.assertIn("GIT_PATCH_ADDED_LINES", candidates[1].evidence_text)
        self.assertEqual(
            "same_commit_source_diff_confirms_lora_implementation",
            evaluate_event_local(
                technology_direction=QUERY.technology_direction,
                title=candidates[1].title,
                text=candidates[1].evidence_text,
            ).reason,
        )
        self.assertFalse(evaluate_event_local(
            technology_direction=QUERY.technology_direction,
            title=candidates[0].title,
            text=candidates[0].evidence_text,
        ).eligible)
        self.assertTrue(any("page=2" in url for url in requests))
        self.assertFalse(any("created_at" in url for url in requests))

    def test_no_same_sha_patch_leaves_bare_support_unverified(self):
        result = evaluate_event_local(
            technology_direction=QUERY.technology_direction,
            title="add lora support",
            text="add lora support",
        )
        self.assertFalse(result.eligible)
        self.assertFalse(evaluate_event_local(
            technology_direction=QUERY.technology_direction,
            title="add lora support",
            text="add lora support\nGIT_PATCH_ADDED_LINES\nFILE radio.cpp\nLoRa wireless gateway",
        ).eligible)


class MultiEventBridgeTests(unittest.TestCase):
    def test_earliest_semantically_accepted_event_wins_and_does_not_double_count(self):
        manager, trend_id, observations = prepared()
        repo = "microsoft/LoRA"
        class History:
            def candidate_events(self, query):
                return (
                    event(repo, "radio", "2020-01-01T00:00:00Z", "Add LoRa radio sensor gateway"),
                    event(repo, "early", "2022-11-30T09:21:26Z",
                        "add lora support\nGIT_PATCH_ADDED_LINES\n"
                        "FILE src/pet/tuners/lora.py\nfrom loralib import mark_only_lora_as_trainable\nLoRAConfig"),
                    event(repo, "later", "2023-02-01T00:00:00Z",
                        "Implement LoRA adapters for transformer language models"),
                )
        bridge = GitHubHistoryBridge(
            history_client=History(),
            embed=lambda texts: [[1.0, 0.0] for _ in texts],
            embedding_model=MODEL,
            policy=GitHubBridgePolicy(experimental_event_local_threshold=0.425),
        )
        result = bridge.enrich(
            manager=manager, trend_id=trend_id,
            observations_by_id=observations, aliases=("lora",),
            distinctive_terms=("LoRA",), now=DATE,
        )
        self.assertEqual(3, len(result.verified_event_ids))
        self.assertEqual(1, len(result.accepted_event_ids))
        self.assertIn("commit:early", result.accepted_event_ids[0])
        self.assertEqual(2, len(result.rejected_event_ids))
        self.assertEqual("2022-11-30T09:21:26Z",
                         manager.states[trend_id].first_evidence_at["implementation"])
        self.assertEqual(3, manager.states[trend_id].observation_count)
        later = [row for row in result.verified_observations if "commit:later" in row["observation_id"]][0]
        self.assertEqual("later_eligible_not_selected", later["quality_flags"]["history_selection"])
        count = manager.states[trend_id].observation_count
        again = bridge.enrich(
            manager=manager, trend_id=trend_id,
            observations_by_id=observations, aliases=("lora",),
            distinctive_terms=("LoRA",), now=DATE,
        )
        self.assertEqual(0, again.update.assignments[0].new_observation_count)
        self.assertEqual(count, manager.states[trend_id].observation_count)


if __name__ == "__main__":
    unittest.main()
