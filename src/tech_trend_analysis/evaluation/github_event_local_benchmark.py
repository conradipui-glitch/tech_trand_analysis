"""Frozen, label-first event-local evaluation; no model training or tuning inside tests."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tech_trend_analysis.github_event_local_gate import evaluate_event_local


def evaluate_gold(path: str | Path = "validation/github_event_gold_v0.json") -> dict[str, Any]:
    corpus = json.loads(Path(path).read_text(encoding="utf-8"))
    if corpus.get("version") != "0.1.0":
        raise ValueError("unexpected gold version")
    directions = corpus["directions"]
    cases = corpus["cases"]
    ids = [row["id"] for row in cases]
    if len(ids) != len(set(ids)) or not cases:
        raise ValueError("gold contains duplicate IDs or no cases")
    by_split: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []
    for row in cases:
        split = row["split"]
        if split not in {"calibration", "holdout"}:
            raise ValueError(f"invalid split: {split}")
        decision = evaluate_event_local(
            technology_direction=directions[row["direction"]],
            title=row["title"],
            text=row["text"],
        )
        predicted = decision.eligible
        expected = bool(row["expected"])
        stat = by_split.setdefault(split, {"tp": 0, "tn": 0, "fp": 0, "fn": 0, "count": 0})
        stat["count"] += 1
        stat["tp" if predicted and expected else "fp" if predicted else "fn" if expected else "tn"] += 1
        diagnostics.append({
            "id": row["id"],
            "split": split,
            "origin": row["origin"],
            "expected": expected,
            "predicted": predicted,
            "reason": decision.reason,
            "evidence_span": decision.evidence_span,
        })
    for stat in by_split.values():
        stat["precision"] = round(stat["tp"] / (stat["tp"] + stat["fp"]), 4) if stat["tp"] + stat["fp"] else None
        stat["recall"] = round(stat["tp"] / (stat["tp"] + stat["fn"]), 4) if stat["tp"] + stat["fn"] else None
        stat["false_positive_rate"] = round(stat["fp"] / (stat["fp"] + stat["tn"]), 4) if stat["fp"] + stat["tn"] else None
    return {"version": corpus["version"], "by_split": by_split, "diagnostics": diagnostics}
