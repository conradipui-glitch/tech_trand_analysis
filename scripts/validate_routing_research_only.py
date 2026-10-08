#!/usr/bin/env python3
"""B-031/B-033 bounded audit: real OpenAlex sample + honest source policy.

Retrospective RAG/LoRA pre-origin search is a *sample*, never proof that
technology did or did not exist before published anchor paper.
No GitHub created_at as origin, no unavailable EPO/HF collector invocation,
no API keys committed and no public score promotion.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from pathlib import Path

from tech_trend_analysis.history_filter import gate_sampled_count
from tech_trend_analysis.source_router import SourceRouter
from run_retrospective_calibration import MonthWindow, OpenAlexHistoryClient


CASES = (
    {
        "id": "rag_pre_origin",
        "query": "retrieval augmented generation",
        "anchor": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        "aliases": ("retrieval augmented generation", "rag"),
        "context": ("knowledge", "language model", "nlp", "retrieval"),
        "start": "2019-11-01", "end": "2019-11-30",
        "known_origin": "2020-05-22",
    },
    {
        "id": "lora_pre_origin",
        "query": "low rank adaptation",
        "anchor": "LoRA Low-Rank Adaptation of Large Language Models",
        "aliases": ("low rank adaptation", "lora"),
        "context": ("llm", "language model", "fine tuning", "transformer", "adapter"),
        "start": "2020-12-01", "end": "2020-12-31",
        "known_origin": "2021-06-17",
    },
    {
        "id": "research_only_present",
        "query": "agentic AI",
        "anchor": "Autonomous AI agents powered by large language models",
        "aliases": ("ai agents", "agentic ai"),
        "context": ("ai", "language model", "llm", "agent"),
        "start": "2026-07-01", "end": "2026-07-31",
        "known_origin": None,
    },
)


def main() -> None:
    router = SourceRouter.from_yaml("config/sources.yaml")
    routing = []
    expected = {
        "AI agents": "software_ai",
        "neuromorphic computing": "hardware_semiconductor",
        "solid-state batteries": "materials_energy",
    }
    for direction, profile in expected.items():
        route = router.route(direction)
        if route.profile != profile:
            raise AssertionError(f"profile regression: {direction} -> {route.profile}")
        routing.append({
            "direction": direction, "profile": route.profile,
            "confidence": route.confidence, "matched_signals": list(route.matched_signals),
            "policy_enabled": [p.provider for p in route.enabled_providers],
            "collector_available": [p.provider for p in route.collectable_providers],
            "blocked": [
                {"provider": p.provider, "reason": p.execution_status}
                for p in route.blocked_providers
            ],
        })
    client = OpenAlexHistoryClient(sample_size=15)
    live = []
    failures = 0
    try:
        for case in CASES:
            try:
                result = client.month(
                    case["query"],
                    MonthWindow(
                        key=case["start"][:7],
                        start=date.fromisoformat(case["start"]),
                        end=date.fromisoformat(case["end"]),
                    ),
                )
                titles = [str(item.get("title") or "") for item in result["samples"]]
                gate = gate_sampled_count(
                    raw_count=result["count"], sample_texts=titles,
                    anchor_text=case["anchor"], aliases=case["aliases"],
                    context_terms=case["context"],
                )
                live.append({
                    "id": case["id"],
                    "status": "observed",
                    "window": [case["start"], case["end"]],
                    "known_research_origin": case["known_origin"],
                    "raw_search_count": result["count"],
                    "sampled_count": gate.sample_count,
                    "accepted_sample_count": gate.matched_sample_count,
                    "estimated_cluster_conditioned_count": gate.estimated_count,
                    "method": "OpenAlex title-only sample gate; not census and not proof of first technology occurrence",
                    "sample": [
                        {"id": item.get("id"), "title": item.get("title"), "accepted": index in gate.accepted_indices}
                        for index, item in enumerate(result["samples"])
                    ],
                })
            except Exception as exc:
                failures += 1
                live.append({"id": case["id"], "status": "request_failed", "error": str(exc)[:300]})
    finally:
        client.close()

    report = {
        "version": "0.1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "routing": routing,
        "openalex_research_only": live,
        "failed_source_queries": failures,
        "scope_limits": [
            "OpenAlex title-only monthly sample is not a complete historical membership/false-positive audit.",
            "Research-only scientific trajectory remains visible, but cannot claim implemented/emerging lifecycle stage.",
            "EPO and HuggingFace provider routes are policy proposals, not installed operational adapters.",
            "Historical technology origin is not inferred from GitHub repository creation dates.",
        ],
    }
    out = Path("validation/results/b031_b033_live.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "routing": [{"direction": row["direction"], "profile": row["profile"],
                     "ready": row["collector_available"], "blocked": row["blocked"]}
                    for row in routing],
        "live": [{"id": row["id"], "status": row["status"],
                  "raw": row.get("raw_search_count"), "accepted": row.get("accepted_sample_count")}
                 for row in live],
    }, ensure_ascii=False, indent=2))
    if failures == len(CASES):
        raise SystemExit("all OpenAlex queries failed; cannot claim live historical sampling")


if __name__ == "__main__":
    main()
