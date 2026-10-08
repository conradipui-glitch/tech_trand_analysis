#!/usr/bin/env python3
"""B-040: independently inspect GitHub PEFT's bounded candidate chronology.

No score updates. Real model validation via Actions artifact; unknown/no
verified event cannot be converted to technology-first date.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.sources.github_history import GitHubHistoryClient, GitHubHistoryQuery


def main() -> None:
    from sentence_transformers import SentenceTransformer

    query = GitHubHistoryQuery(
        repository="huggingface/peft",
        technology_direction="low-rank adaptation of large language models",
        source_profile="software_ai",
        aliases=("lora", "low rank adaptation"),
        distinctive_terms=("LoRA",),
        context_terms=("support", "adapter", "peft", "llm"),
        query_id="b040:peft:chronological",
    )
    with GitHubHistoryClient(token=os.environ.get("GITHUB_TOKEN")) as client:
        events = client.candidate_events(
            query,
            max_candidates=30,
            commit_pages_per_term=2,
            max_diff_checks=9,
        )
    model = SentenceTransformer("BAAI/bge-m3")
    decisions = [
        evaluate_event_local(
            technology_direction=query.technology_direction,
            title=event.title,
            text=event.evidence_text or event.title,
        )
        for event in events
    ]
    texts = [decision.evidence_span or (event.evidence_text or event.title)
             for event, decision in zip(events, decisions, strict=True)]
    model_inputs = [query.technology_direction, *texts]
    if events:
        vectors = np.asarray(model.encode(model_inputs, normalize_embeddings=True), dtype=np.float32)
        cosines = vectors[1:] @ vectors[0]
    else:
        cosines = []
    threshold = 0.425  # B-039 experimental calibration, NOT prod
    results = []
    for event, decision, cosine in zip(events, decisions, cosines, strict=True):
        similarity = float(cosine)
        accept = decision.eligible and similarity >= threshold
        results.append({
            "repository": event.repository,
            "event_kind": event.event_kind,
            "event_id": event.external_id,
            "occurred_at": event.occurred_at,
            "url": event.url,
            "title": event.title,
            "evidence_excerpt": (event.evidence_text or event.title)[:1500],
            "local_span": decision.evidence_span,
            "reason": decision.reason,
            "local_gate": decision.status,
            "similarity_to_direction": round(similarity, 5),
            "accepted_experimentally": accept,
        })
    first = next((result for result in results if result["accepted_experimentally"]), None)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": "BAAI/bge-m3",
        "query": query.technology_direction,
        "repository": query.repository,
        "candidate_count": len(results),
        "experimental_threshold": threshold,
        "first_accepted_in_bounded_window": first,
        "known_earlier_event_for_audit": {
            "sha": "e8160370247b3b61f57e59eb3f49acf9e3618b4b",
            "date": "2022-11-30T09:21:26Z",
        },
        "not_claimed": "globally first ever LoRA implementation",
        "events": results,
    }
    dest = Path("validation/results/github-chronology-peft.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "repository": query.repository,
        "candidate_count": len(results),
        "locally_eligible_count": sum(d.eligible for d in decisions),
        "accepted_count": sum(v["accepted_experimentally"] for v in results),
        "first_accepted": None if first is None else {
            "sha": first["event_id"], "date": first["occurred_at"],
            "similarity": first["similarity_to_direction"],
        },
        "known_nov_2022_commit_in_candidate_pool": any(
            v["event_id"] == "e8160370247b3b61f57e59eb3f49acf9e3618b4b" for v in results
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
