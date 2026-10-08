#!/usr/bin/env python3
"""B-043 real GitHub LoRA-module lineage experiment; NO TrendState updates."""
from __future__ import annotations

import json
import os
from pathlib import Path

from sentence_transformers import SentenceTransformer

from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.github_module_lineage import GitModuleLineageVerifier
from tech_trend_analysis.github_patch_evidence import extract_source_patch
from tech_trend_analysis.sources.github_history import GitHubHistoryClient, VerifiedGitEvent


def event(client, repository: str, sha: str, *, with_source: bool) -> VerifiedGitEvent:
    payload = client._get_json(f"/repos/{repository}/commits/{sha}")
    if payload.get("sha") != sha:
        raise ValueError("GitHub supplied wrong SHA")
    commit = payload["commit"]
    date = (commit.get("committer") or {}).get("date")
    if not date:
        raise ValueError("no timestamp on Git commit")
    msg = str(commit.get("message") or "").strip()
    return VerifiedGitEvent(
        repository=repository, event_kind="commit", external_id=sha,
        occurred_at=date, title=msg.splitlines()[0],
        evidence_text=msg,
        source_diff=extract_source_patch(payload.get("files") or []) if with_source else None,
        url=payload["html_url"], matched_terms=("lora",),
        source_endpoint="GET /commits/{sha}",
    )


def counts(rows):
    return {
        "tp": sum(r["expected"] and r["predicted"] for r in rows),
        "fp": sum(not r["expected"] and r["predicted"] for r in rows),
        "tn": sum(not r["expected"] and not r["predicted"] for r in rows),
        "fn": sum(r["expected"] and not r["predicted"] for r in rows),
    }


def main():
    payload = json.loads(Path("validation/github_module_lineage_v1.json").read_text())
    direction = payload["technology_direction"]
    with GitHubHistoryClient(token=os.environ.get("GITHUB_TOKEN")) as client:
        anchor = event(client, payload["anchor"]["repository"], payload["anchor"]["sha"], with_source=True)
        if not anchor.source_diff:
            raise RuntimeError("anchor has no same-SHA source evidence")
        anchor_gate = evaluate_event_local(
            technology_direction=direction, title=anchor.title,
            text=anchor.evidence_text or anchor.title, source_diff=anchor.source_diff
        )
        if not anchor_gate.eligible:
            raise RuntimeError("anchor is not confirmed as relevant LoRA source evidence")
        model = SentenceTransformer("BAAI/bge-m3")
        vectors = model.encode(
            [direction, anchor_gate.evidence_span],
            normalize_embeddings=True, show_progress_bar=False,
        )
        similarity = float(vectors[0] @ vectors[1])
        verifier = GitModuleLineageVerifier(client)
        rows = []
        for case in payload["cases"]:
            cand = event(client, case["repository"], case["sha"], with_source=False)
            outcome = verifier.verify(
                technology_direction=direction, anchor=anchor, candidate=cand
            )
            rows.append({
                "id": case["id"], "repository": case["repository"],
                "candidate_sha": case["sha"], "expected": case["expected"],
                "predicted": outcome.supporting, "reason": outcome.reason,
                "lineage_status": outcome.verdict,
                "matched_source_paths": outcome.source_paths,
                "added_line_samples": outcome.added_line_samples,
                "candidate_timestamp": cand.occurred_at,
            })
    results = {
        "version": payload["version"], "anchor_sha": anchor.external_id,
        "anchor_timestamp": anchor.occurred_at,
        "anchor_gated": anchor_gate.reason,
        "anchor_similarity": round(similarity, 5),
        "anchor_embedding_threshold_unchanged": 0.425,
        "frozen_label_sample_size": len(rows),
        "metrics": counts(rows), "cases": rows,
        "not_for_scoring": True,
        "limitations": payload["selection"],
    }
    path = Path("validation/results/github_module_lineage_v1.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({
        "anchor_similarity": results["anchor_similarity"],
        "metrics": results["metrics"],
        "cases": [
            {"id":r["id"],"predicted":r["predicted"],"reason":r["reason"]}
            for r in rows
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
