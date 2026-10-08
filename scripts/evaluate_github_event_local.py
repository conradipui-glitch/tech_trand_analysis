#!/usr/bin/env python3
"""Produce reproducible confusion matrices and reasons for B-039."""
from __future__ import annotations
import json
from pathlib import Path

from tech_trend_analysis.evaluation.github_event_local_benchmark import evaluate_gold


def main() -> None:
    report = evaluate_gold()
    output = Path("validation/results/github_event_local_benchmark_v0.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["by_split"], indent=2))
    for row in report["diagnostics"]:
        if row["predicted"] != row["expected"]:
            print("MISMATCH", row["id"], "expected", row["expected"], "reason", row["reason"])


if __name__ == "__main__":
    main()
