"""B-045 bounded cross-commit rename proof; never infer from similar paths."""
import unittest
import httpx

from tech_trend_analysis.github_rename_lineage import trace_renamed_module
from tech_trend_analysis.github_module_lineage import GitModuleLineageVerifier
from tech_trend_analysis.sources.github_history import GitHubHistoryClient, VerifiedGitEvent

REPO="example/lineage"
DIRECTION="low-rank adaptation of large language models"
ANCHOR=VerifiedGitEvent(
    repository=REPO,event_kind="commit",external_id="anchor",
    occurred_at="2023-01-01T00:00:00Z",title="Implement LoRA transformer adapters",
    url="https://github.com/example/lineage/commit/anchor",
    matched_terms=("lora",),source_endpoint="GET /commits/anchor",
    evidence_text="Implement LoRA adapters for transformer language models",
    source_diff="FILE src/pet/tuners/lora.py\n+class LoRAConfig:\n+from loralib import mark_only_lora_as_trainable",
)
CANDIDATE=VerifiedGitEvent(
    repository=REPO,event_kind="commit",external_id="candidate",
    occurred_at="2023-04-01T00:00:00Z",title="Add modules_to_save to LoraConfig",
    url="https://github.com/example/lineage/commit/candidate",
    matched_terms=("lora",),source_endpoint="GET /commits/candidate",
    evidence_text="Add modules_to_save to LoraConfig and other fixes",
)


def fixture(*,two_hops=False, rename_status="renamed", graph="ahead", history_full=False, source_patch=True):
    logs=[]
    paths=[
        ("src/pet/tuners/lora.py","src/peft/tuners/lora.py","move1"),
    ] if not two_hops else [
        ("src/pet/tuners/lora.py","src/peft/lora.py","move1"),
        ("src/peft/lora.py","src/peft/tuners/lora.py","move2"),
    ]
    def response(request):
        logs.append(str(request.url))
        p=request.url.path
        if p==f"/repos/{REPO}/compare/anchor...candidate":
            return httpx.Response(200,json={"status":"ahead"})
        if "/compare/" in p:
            return httpx.Response(200,json={"status":graph})
        if p==f"/repos/{REPO}/commits/candidate":
            return httpx.Response(200,json={
                "sha":"candidate",
                "files":[{
                    "filename":"src/peft/tuners/lora.py","status":"modified",
                    "patch":"+    modules_to_save = config.lora_target_modules" if source_patch else "+# comment only",
                }],
            })
        if p==f"/repos/{REPO}/commits":
            search=request.url.params.get("path")
            item=next((sh for old,new,sh in paths if old==search),None)
            if item is None:return httpx.Response(200,json=[])
            if history_full:
                return httpx.Response(200,json=[
                    {"sha":item,"commit":{"committer":{"date":"2023-02-01T00:00:00Z"}}},
                    {"sha":"placeholder","commit":{"committer":{"date":"2023-02-01T00:00:00Z"}}}
                ])
            date="2023-02-01T00:00:00Z" if item=="move1" else "2023-03-01T00:00:00Z"
            return httpx.Response(200,json=[{"sha":item,"commit":{"committer":{"date":date}}}])
        if p in (f"/repos/{REPO}/commits/move1",f"/repos/{REPO}/commits/move2"):
            sha=p.rsplit("/",1)[-1]
            old,new,_=next(row for row in paths if row[2]==sha)
            date="2023-02-01T00:00:00Z" if sha=="move1" else "2023-03-01T00:00:00Z"
            return httpx.Response(200,json={
                "sha":sha,"commit":{"committer":{"date":date}},
                "files":[{"filename":new,"previous_filename":old,"status":rename_status}]
            })
        raise AssertionError(str(request.url))
    return httpx.MockTransport(response),logs


class RenameChainTests(unittest.TestCase):
    def run_fixture(self, **opts):
        transport,logs=fixture(**opts)
        with GitHubHistoryClient(transport=transport,max_retries=0) as client:
            result=GitModuleLineageVerifier(client).verify(
                technology_direction=DIRECTION,anchor=ANCHOR,candidate=CANDIDATE)
        return result,logs

    def test_real_declared_single_rename_between_two_commits(self):
        r,log=self.run_fixture()
        self.assertTrue(r.supporting)
        self.assertEqual("confirmed_ancestor_and_bounded_rename_chain",r.reason)
        self.assertEqual(("move1","src/pet/tuners/lora.py","src/peft/tuners/lora.py"),
                         r.verified_renames[0])
        self.assertEqual(1,len(r.verified_renames))
        self.assertTrue(any("compare/move1...candidate" in url for url in log))

    def test_multi_hop_git_commit_renames(self):
        r,log=self.run_fixture(two_hops=True)
        self.assertTrue(r.supporting)
        self.assertEqual(2,len(r.verified_renames))
        self.assertEqual("move2",r.verified_renames[-1][0])

    def test_similar_filename_without_renamed_status_is_not_proof(self):
        r,_=self.run_fixture(rename_status="modified")
        self.assertFalse(r.supporting)
        self.assertEqual("no_executable_changes_to_confirmed_module",r.reason)

    def test_branch_divergence_blocks_apparent_rename(self):
        r,_=self.run_fixture(graph="diverged")
        self.assertFalse(r.supporting)

    def test_no_executable_code_in_candidate_still_rejects(self):
        r,_=self.run_fixture(source_patch=False)
        self.assertFalse(r.supporting)

    def test_full_history_page_fails_closed(self):
        trans, _=fixture(history_full=True)
        with GitHubHistoryClient(transport=trans,max_retries=0) as client:
            result=trace_renamed_module(
                client,repository=REPO,anchor_sha="anchor",candidate_sha="candidate",
                anchor_time=ANCHOR.occurred_at,candidate_time=CANDIDATE.occurred_at,
                paths=("src/pet/tuners/lora.py",),
                candidate_paths=("src/peft/tuners/lora.py",),
                max_history=2,
            )
        self.assertFalse(result.complete)
        self.assertEqual("truncated_git_history",result.reason)


if __name__=="__main__":
    unittest.main()
