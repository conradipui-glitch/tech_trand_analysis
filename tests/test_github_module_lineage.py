import unittest

import httpx

from tech_trend_analysis.github_module_lineage import (
    GitModuleLineageVerifier, source_anchor_paths,
)
from tech_trend_analysis.sources.github_history import (
    GitHubHistoryClient, VerifiedGitEvent,
)

REPO = "example/ml-project"
ANCHOR = VerifiedGitEvent(
    repository=REPO, event_kind="commit", external_id="a1",
    occurred_at="2023-03-01T00:00:00Z",
    title="Implement LoRA transformer adapters",
    evidence_text="Implement LoRA transformer language model adapters",
    source_diff="FILE ml/lora_adapter.py\n+class LoRAConfig:\n+get_peft_model(model)",
    url="https://github.com/example/ml-project/commit/a1",
    matched_terms=("LoRA",), source_endpoint="GET /search/commits",
)
CANDIDATE = VerifiedGitEvent(
    repository=REPO, event_kind="commit", external_id="b2",
    occurred_at="2023-04-01T00:00:00Z",
    title="Fix tokenizer issue",
    evidence_text="Fix tokenizer issue",
    url="https://github.com/example/ml-project/commit/b2",
    matched_terms=("LoRA",), source_endpoint="GET /search/commits",
)
DIRECTION = "low-rank adaptation of large language models"


def mock_history(status="ahead", files=None, sha="b2"):
    calls = []
    def handler(req):
        calls.append(req.url.path)
        if "/compare/" in req.url.path:
            return httpx.Response(200, json={"status": status})
        if req.url.path.endswith("/commits/b2"):
            return httpx.Response(200, json={
                "sha": sha,
                "files": files if files is not None else [
                    {"filename": "ml/lora_adapter.py", "status": "modified",
                     "patch": "@@ -1,2 +1,3 @@\n+tokenizer = load_fast_tokenizer(config)"},
                ],
            })
        if req.url.path == "/repos/example/ml-project/commits":
            return httpx.Response(200, json=[])
        raise AssertionError(str(req.url))
    return GitHubHistoryClient(transport=httpx.MockTransport(handler), max_retries=0), calls


class ModuleLineageTests(unittest.TestCase):
    def test_confirmed_descendant_changes_anchored_module_not_new_adopter(self):
        client, calls = mock_history()
        with client:
            result = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
            )
        self.assertTrue(result.supporting)
        self.assertEqual("confirmed_ancestor_and_same_module_source_change", result.reason)
        self.assertEqual(("ml/lora_adapter.py",), result.source_paths)
        self.assertEqual("2023-03-01T00:00:00Z", result.original_anchor_timestamp)
        self.assertEqual("2023-04-01T00:00:00Z", result.candidate_timestamp)
        self.assertEqual(2, len(calls))
        self.assertTrue(any("/compare/a1...b2" in path for path in calls))

    def test_unrelated_file_or_docs_only_not_support(self):
        for files in (
            [{"filename": "ml/other_module.py", "patch": "+tokenizer = fix()", "status": "modified"}],
            [{"filename": "docs/lora_adapter.py", "patch": "+tokenizer = fix()", "status": "modified"}],
            [{"filename": "ml/lora_adapter.py", "patch": "-old = 1\n+# comment", "status": "modified"}],
            [{"filename": "ml/lora_adapter.py", "patch": "-removed = 1", "status": "modified"}],
        ):
            client, _ = mock_history(files=files)
            with client:
                result = GitModuleLineageVerifier(client).verify(
                    technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
                )
            self.assertEqual("no_executable_changes_to_confirmed_module", result.reason)

    def test_cross_repository_and_backdating_fail_before_network(self):
        wrong_repo = VerifiedGitEvent(
            **{**CANDIDATE.__dict__, "repository": "unrelated/repo"}
        ) if hasattr(CANDIDATE, "__dict__") else None
        # Frozen slots dataclass can be copied safely via replace.
        from dataclasses import replace
        client, calls = mock_history()
        with client:
            for candidate in (
                replace(CANDIDATE, repository="unrelated/repo"),
                replace(CANDIDATE, occurred_at="2020-01-01T00:00:00Z"),
                replace(CANDIDATE, external_id="a1"),
            ):
                result = GitModuleLineageVerifier(client).verify(
                    technology_direction=DIRECTION, anchor=ANCHOR, candidate=candidate,
                )
                self.assertFalse(result.supporting)
        self.assertEqual([], calls)

    def test_commit_graph_divergence_not_enough_to_share_file(self):
        for status in ("diverged", "behind", "identical"):
            client, calls = mock_history(status=status)
            with client:
                result = GitModuleLineageVerifier(client).verify(
                    technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
                )
            self.assertFalse(result.supporting)
            self.assertEqual("not_confirmed_descendant", result.reason)
            self.assertEqual(1, len(calls))

    def test_explicit_same_sha_rename_can_preserve_lineage(self):
        files = [{
            "filename": "ml/adapters/lora.py",
            "previous_filename": "ml/lora_adapter.py",
            "status": "renamed",
            "patch": "@@ -1,1 +1,2 @@\n+tokenizer = tokenizer_v2(config)",
        }]
        client, _ = mock_history(files=files)
        with client:
            result = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
            )
        self.assertTrue(result.supporting)
        self.assertEqual(("ml/adapters/lora.py",), result.source_paths)

    def test_synthetic_rename_claim_without_github_status_rejected(self):
        files = [{
            "filename": "ml/adapters/lora.py",
            "previous_filename": "ml/lora_adapter.py",
            "status": "modified",
            "patch": "+x = 123",
        }]
        client, _ = mock_history(files=files)
        with client:
            result = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
            )
        self.assertFalse(result.supporting)

    def test_missing_anchor_proof_and_false_anchor_fail_closed(self):
        from dataclasses import replace
        client, calls = mock_history()
        with client:
            for anchor in (
                replace(ANCHOR, source_diff=None),
                replace(ANCHOR, source_diff="FILE README.md\n+class LoRAConfig:"),
                replace(ANCHOR, title="LoRa wireless radio support",
                        evidence_text="LoRa radio sensor gateway"),
            ):
                result = GitModuleLineageVerifier(client).verify(
                    technology_direction=DIRECTION, anchor=anchor, candidate=CANDIDATE,
                )
                self.assertFalse(result.supporting)
        self.assertEqual([], calls)

    def test_shared_utils_file_must_change_technology_related_code(self):
        from dataclasses import replace
        anchor = replace(
            ANCHOR, source_diff="FILE trl/trainer/utils.py\n+target_modules=model_config.lora_target_modules"
        )
        # The base candidate is a regular change in utils.py, not evidence
        # of an additional LoRA change.
        generic_file = [{
            "filename": "trl/trainer/utils.py",
            "patch": "@@ def create_model_from_path @@\n+dtype = kwargs.get('dtype', 'auto')",
        }]
        client, _ = mock_history(files=generic_file)
        with client:
            outcome = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=anchor, candidate=CANDIDATE,
            )
        self.assertFalse(outcome.supporting)

        lora_file = [{
            "filename": "trl/trainer/utils.py",
            "patch": "@@ def get_peft_config @@\n+target_parameters=model_args.lora_target_parameters",
        }]
        client, _ = mock_history(files=lora_file)
        with client:
            outcome = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=anchor, candidate=CANDIDATE,
            )
        self.assertTrue(outcome.supporting)

    def test_missing_candidate_sha_is_not_proof(self):
        client, _ = mock_history(sha="spoof")
        with client:
            result = GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION, anchor=ANCHOR, candidate=CANDIDATE,
            )
        self.assertEqual("candidate_commit_sha_mismatch", result.reason)

    def test_source_path_excludes_nonmodules(self):
        paths = source_anchor_paths(
            "FILE docs/foo.py\n+class LoRAConfig:\n"
            "FILE ml/lora.py\n+LoRAConfig()\n"
            "FILE tests/test_lora.py\n+LoRAConfig()\n"
        )
        self.assertEqual(("ml/lora.py",), paths)


if __name__ == "__main__":
    unittest.main()
