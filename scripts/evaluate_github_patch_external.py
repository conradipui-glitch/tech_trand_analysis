#!/usr/bin/env python3
"""B-042: evaluate frozen NEW Git commit SHAs against live same-SHA diffs.

Frozen labels are never trained upon or updated here. The 0.425 threshold is
exactly the previous B-039 value; no refit. No production TrendState mutation.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import quote

import httpx
import numpy as np
from sentence_transformers import SentenceTransformer

from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.github_patch_evidence import extract_source_patch


def metrics(rows, field):
    tp = tn = fp = fn = 0
    for row in rows:
        expected = bool(row["expected"])
        predicted = bool(row[field])
        if predicted and expected:
            tp += 1
        elif predicted:
            fp += 1
        elif expected:
            fn += 1
        else:
            tn += 1
    return {
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def fetch_commit(client, repo, sha):
    url = f"/repos/{repo}/commits/{quote(sha, safe='')}"
    for attempt in range(4):
        response = client.get(url)
        if response.status_code in (403, 429, 502, 503, 504) and attempt < 3:
            time.sleep(min(3 * (attempt + 1), 10))
            continue
        response.raise_for_status()
        obj = response.json()
        if obj.get("sha") != sha or not isinstance(obj.get("files"), list):
            raise ValueError(f"GitHub commit SHA / files mismatch for {repo}")
        return obj
    raise RuntimeError("commit fetch exhausted retries")


def main():
    path = Path("validation/github_patch_external_v2.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data["cases"]
    if len(set(row["sha"] for row in rows)) != len(rows):
        raise ValueError("duplicate commit SHA")
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tech-trend-analysis/0.1",
    }
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    model_input = []
    evidence = []
    with httpx.Client(base_url="https://api.github.com", headers=headers, timeout=30) as client:
        for row in rows:
            commit = fetch_commit(client, row["repository"], row["sha"])
            message = str(commit.get("commit", {}).get("message") or "")
            title = message.splitlines()[0].strip()
            source_diff = extract_source_patch(commit["files"])
            direction = data["technology_directions"][row["family"]]
            base = evaluate_event_local(
                technology_direction=direction, title=title, text=message,
            )
            patched = evaluate_event_local(
                technology_direction=direction, title=title, text=message,
                source_diff=source_diff,
            )
            evidence.append({
                "id": row["id"], "url": row["url"], "sha": row["sha"],
                "repository": row["repository"], "expected": row["expected"],
                "title": title,
                "baseline_gate": base.status, "patch_gate": patched.status,
                "patch_reason": patched.reason,
                "patch_available": source_diff is not None,
                "patch_excerpt": (source_diff or "")[:850],
                "matched_span": patched.evidence_span,
            })
            model_input.append((direction, base.evidence_span or title,
                                patched.evidence_span or title))
    model = SentenceTransformer("BAAI/bge-m3")
    strings = [x[0] for x in model_input] + [x[1] for x in model_input] + [
        x[2] for x in model_input
    ]
    vec = np.asarray(model.encode(strings, normalize_embeddings=True, show_progress_bar=False))
    n = len(evidence)
    sim_base = (vec[:n] * vec[n:2*n]).sum(axis=1)
    sim_patch = (vec[:n] * vec[2*n:]).sum(axis=1)
    threshold = 0.425
    for row, baseline_score, patched_score in zip(
        evidence, sim_base.tolist(), sim_patch.tolist(), strict=True
    ):
        row["baseline_cosine"] = round(float(baseline_score), 5)
        row["patch_cosine"] = round(float(patched_score), 5)
        row["baseline_predicted"] = row["baseline_gate"] == "eligible" and baseline_score >= threshold
        row["patched_predicted"] = row["patch_gate"] == "eligible" and patched_score >= threshold
    base_stats = metrics(evidence, "baseline_predicted")
    patch_stats = metrics(evidence, "patched_predicted")
    result = {
        "version": data["version"],
        "frozen_gold": str(path),
        "model": "BAAI/bge-m3",
        "fixed_threshold": threshold,
        "parameters_tuned_on_this_set": False,
        "sample_limitations": data["limitations"],
        "baseline": base_stats, "patched": patch_stats,
        "cases": evidence,
    }
    out = Path("validation/results/github_patch_external_v2.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "baseline": base_stats, "patched": patch_stats,
        "errors": [
            {"id": row["id"], "expected": row["expected"],
             "predicted": row["patched_predicted"], "reason": row["patch_reason"],
             "cosine": row["patch_cosine"], "patch_available": row["patch_available"]}
            for row in evidence if row["expected"] != row["patched_predicted"]
        ],
        "report": str(out),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
