#!/usr/bin/env python3
"""Independent-of-B044-repositories live evaluation of fixed B-045 lineage gate.

This is a held-aside convenience cohort, NOT randomized/blind validation.
No scoring or TrendState changes; all decisions and source references are kept.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import quote

from tech_trend_analysis.github_module_lineage import GitModuleLineageVerifier
from tech_trend_analysis.github_patch_evidence import extract_source_patch
from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.sources.github_history import GitHubHistoryClient, VerifiedGitEvent


def event(client: GitHubHistoryClient, repo: str, sha: str, with_diff: bool) -> VerifiedGitEvent:
    data = client._get_json(f"/repos/{repo}/commits/{quote(sha, safe='')}")
    if not isinstance(data, dict) or data.get("sha") != sha:
        raise ValueError(f"GitHub response SHA mismatch: {repo}@{sha}")
    metadata = data.get("commit") or {}
    occurred = (metadata.get("committer") or {}).get("date")
    message = metadata.get("message")
    if not isinstance(occurred, str) or not isinstance(message, str):
        raise ValueError("Missing immutable commit message or committer time")
    return VerifiedGitEvent(
        repository=repo, event_kind="commit", external_id=sha,
        occurred_at=occurred, title=message.splitlines()[0] or sha[:10],
        evidence_text=message,
        source_diff=extract_source_patch(data.get("files") or ()) if with_diff else None,
        source_endpoint="GET /repos/{repo}/commits/{sha}",
        matched_terms=(), url=data.get("html_url") or f"https://github.com/{repo}/commit/{sha}",
    )


def main() -> None:
    corpus_path = Path("validation/github_module_lineage_unseen_v4.json")
    cohort = json.loads(corpus_path.read_text(encoding="utf-8"))
    if cohort.get("version") != "0.1.0":
        raise ValueError("Unexpected cohort revision")
    cases = []
    with GitHubHistoryClient(token=os.getenv("GITHUB_TOKEN")) as client:
        verifier = GitModuleLineageVerifier(client)
        for group in cohort["groups"]:
            repo = group["repository"]
            direction = group["technology_direction"]
            anchor = event(client, repo, group["anchor_sha"], True)
            gate = evaluate_event_local(
                technology_direction=direction,
                title=anchor.title, text=anchor.evidence_text or anchor.title,
                source_diff=anchor.source_diff,
            )
            if not gate.eligible:
                raise ValueError(f"Frozen anchor not source-verified: {repo} ({gate.reason})")
            for item in group["cases"]:
                candidate = event(client, repo, item["sha"], False)
                decision = verifier.verify(
                    technology_direction=direction, anchor=anchor,
                    candidate=candidate,
                )
                cases.append({
                    "repository": repo,
                    "direction": direction,
                    "anchor_sha": anchor.external_id,
                    "candidate_sha": candidate.external_id,
                    "candidate_url": candidate.url,
                    "anchor_time": anchor.occurred_at,
                    "candidate_time": candidate.occurred_at,
                    "expected": item["expected"],
                    "predicted": decision.supporting,
                    "decision": decision.verdict,
                    "reason": decision.reason,
                    "source_paths": list(decision.source_paths),
                    "verified_renames": [
                        {"sha": sha, "from": old, "to": new}
                        for sha, old, new in decision.verified_renames
                    ],
                })
    stats = {
        "tp": sum(bool(x["expected"] and x["predicted"]) for x in cases),
        "fp": sum(bool(not x["expected"] and x["predicted"]) for x in cases),
        "tn": sum(bool(not x["expected"] and not x["predicted"]) for x in cases),
        "fn": sum(bool(x["expected"] and not x["predicted"]) for x in cases),
    }
    output = Path("validation/results/github_module_lineage_unseen_v4.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "cohort": str(corpus_path), "count": len(cases), "statistics": stats,
        "cases": cases, "limitations": cohort["limitations"],
        "score_integration": False,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "count": len(cases), **stats,
        "errors": [
            {"repo": row["repository"], "sha": row["candidate_sha"],
             "reason": row["reason"], "expected": row["expected"]}
            for row in cases if row["expected"] != row["predicted"]
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
