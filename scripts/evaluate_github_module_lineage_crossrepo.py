#!/usr/bin/env python3
"""B-044 real GitHub multi-repository module lineage diagnostic.

Frozen labels are never fitted. The verifier does not mutate TrendState,
scores, actors, first_seen, or user-facing snapshots.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

from tech_trend_analysis.github_patch_evidence import extract_source_patch
from tech_trend_analysis.github_module_lineage import GitModuleLineageVerifier
from tech_trend_analysis.sources.github_history import GitHubHistoryClient, VerifiedGitEvent


def get_event(client: GitHubHistoryClient, repo: str, sha: str, *, source: bool) -> VerifiedGitEvent:
    payload=client._get_json(f"/repos/{repo}/commits/{quote(sha, safe='')}")
    if payload.get("sha") != sha:
        raise ValueError(f"GitHub SHA mismatch for {repo} {sha}")
    c=payload.get("commit") or {}
    dt=(c.get("committer") or {}).get("date")
    if not dt:
        raise ValueError("GitHub commit lacks dated committer event")
    msg=str(c.get("message") or "")
    return VerifiedGitEvent(
        repository=repo, event_kind="commit", external_id=sha,
        occurred_at=dt, title=msg.splitlines()[0] if msg else "No subject",
        evidence_text=msg, source_diff=extract_source_patch(payload.get("files") or []) if source else None,
        url=str(payload.get("html_url") or f"https://github.com/{repo}/commit/{sha}"),
        matched_terms=("LoRA",), source_endpoint=f"GET /repos/{repo}/commits/{sha}",
    )


def main():
    spec=json.loads(Path(os.getenv("LINEAGE_CASE_FILE", "validation/github_module_lineage_crossrepo_v2.json")).read_text(encoding="utf-8"))
    cases=[]
    with GitHubHistoryClient(token=os.getenv("GITHUB_TOKEN"), max_retries=3) as client:
        verifier=GitModuleLineageVerifier(client)
        for group in spec["anchors"]:
            anchor=get_event(client,group["repo"],group["sha"],source=True)
            for item in group["cases"]:
                repository=item.get("repository",group["repo"])
                candidate=get_event(client,repository,item["sha"],source=False)
                result=verifier.verify(
                    technology_direction=spec["technology_direction"],
                    anchor=anchor,candidate=candidate,
                )
                cases.append({
                    "repo":group["repo"],"anchor_sha":anchor.external_id,
                    "candidate_sha":candidate.external_id,"candidate_repo":repository,
                    "anchor_time":anchor.occurred_at,"candidate_time":candidate.occurred_at,
                    "expected":item["expected"],"actual":result.supporting,
                    "decision":result.verdict,"reason":result.reason,
                    "paths":list(result.source_paths),"samples":list(result.added_line_samples),
                    "verified_renames":[{"sha":sha,"from":old,"to":new} for sha,old,new in result.verified_renames],
                    "url":candidate.url,
                })
    tp=sum(1 for r in cases if r["expected"] and r["actual"])
    fp=sum(1 for r in cases if not r["expected"] and r["actual"])
    fn=sum(1 for r in cases if r["expected"] and not r["actual"])
    tn=sum(1 for r in cases if not r["expected"] and not r["actual"])
    report={
        "version":"0.1.0","source":"GitHub public commit+compare API",
        "tp":tp,"fp":fp,"fn":fn,"tn":tn,"cases":cases,
        "limitations":"Hand-selected, tiny multi-repository first-pass validation; not blind generalization.",
        "score_integration":False,
    }
    dest=Path(os.getenv("LINEAGE_OUTPUT_FILE", "validation/results/github_module_lineage_crossrepo_v2.json"))
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({
        "tp":tp,"fp":fp,"fn":fn,"tn":tn,
        "failed":[{"repo":r["repo"],"sha":r["candidate_sha"],"reason":r["reason"]}
                  for r in cases if r["actual"] != r["expected"]],
    },indent=2))


if __name__=="__main__":
    main()
