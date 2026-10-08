#!/usr/bin/env python3
"""B-039 paired BGE-M3 audit of raw vs event-local texts.

Never automatically tunes production model thresholds. This diagnostic uses the
labeled corpus and prints calibration and holdout separately. Corpus is small,
partly synthetic and manually authored with knowledge of the examples.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from tech_trend_analysis.github_event_local_gate import evaluate_event_local


def _metrics(rows, scores, lexical, *, threshold: float):
    tp = fp = tn = fn = 0
    samples = []
    for row, similarity, flag in zip(rows, scores, lexical, strict=True):
        prediction = flag and similarity >= threshold
        expected = row["expected"]
        if prediction and expected:
            tp += 1
        elif prediction:
            fp += 1
        elif expected:
            fn += 1
        else:
            tn += 1
        samples.append({
            "id": row["id"],
            "expected": expected,
            "predicted": prediction,
            "local_gate": flag,
            "similarity": round(float(similarity), 5),
        })
    return {
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": (tp / (tp + fp)) if (tp + fp) else None,
        "recall": (tp / (tp + fn)) if (tp + fn) else None,
        "samples": samples,
    }


def main():
    data = json.loads(Path("validation/github_event_gold_v0.json").read_text(encoding="utf-8"))
    cases = data["cases"]
    directions = data["directions"]
    raw_texts = [(row["title"] + " " + row["text"])[:4000] for row in cases]
    decisions = [evaluate_event_local(
        technology_direction=directions[row["direction"]],
        title=row["title"], text=row["text"],
    ) for row in cases]
    local_texts = [decision.evidence_span or row["title"] for row, decision in zip(cases, decisions, strict=True)]
    model = SentenceTransformer("BAAI/bge-m3")
    texts = [
        *[directions[row["direction"]] for row in cases],
        *raw_texts,
        *local_texts,
    ]
    vectors = np.asarray(model.encode(texts, normalize_embeddings=True, show_progress_bar=False), dtype=np.float32)
    n = len(cases)
    anchors, raw, local = vectors[:n], vectors[n:2*n], vectors[2*n:]
    raw_similarity = np.sum(anchors * raw, axis=1).tolist()
    local_similarity = np.sum(anchors * local, axis=1).tolist()
    eligible = [decision.eligible for decision in decisions]

    calibration = [i for i, x in enumerate(cases) if x["split"] == "calibration"]
    holdout = [i for i, x in enumerate(cases) if x["split"] == "holdout"]

    def subset(idx):
        return [cases[i] for i in idx], [eligible[i] for i in idx]

    calibration_rows, calibration_lexical = subset(calibration)
    holdout_rows, holdout_lexical = subset(holdout)
    thresholds = [round(x * 0.025, 3) for x in range(12, 35)]  # 0.30..0.85
    # Pre-declared selection rule: highest threshold achieving zero false
    # positives AND >=80% recall on calibration. Not fitted on holdout.
    options = []
    for threshold in thresholds:
        m = _metrics(calibration_rows, [local_similarity[i] for i in calibration],
                     calibration_lexical, threshold=threshold)
        if m["fp"] == 0 and (m["recall"] or 0) >= 0.8:
            options.append(threshold)
    selected = max(options) if options else None

    report = {
        "version": "0.1.0",
        "model": "BAAI/bge-m3",
        "notes": "Small manually curated + partly synthetic corpus; not a blinded evaluation. Threshold is experiment-only.",
        "threshold_rule": "max local BGE threshold with zero calibration FP and >=0.80 calibration recall",
        "selected_local_threshold": selected,
        "records": [{
            "id": row["id"], "split": row["split"], "origin": row["origin"],
            "expected": row["expected"], "local_gate": decision.status,
            "raw_to_direction": round(float(rs), 5),
            "local_to_direction": round(float(ls), 5),
            "evidence_span": decision.evidence_span,
        } for row, decision, rs, ls in zip(cases, decisions, raw_similarity, local_similarity, strict=True)],
        "evaluation": {},
    }
    if selected is not None:
        for split, idx, rows, flags in (
            ("calibration", calibration, calibration_rows, calibration_lexical),
            ("holdout", holdout, holdout_rows, holdout_lexical),
        ):
            report["evaluation"][split] = {
                "raw_plus_local_gate": _metrics(
                    rows, [raw_similarity[i] for i in idx], flags, threshold=selected
                ),
                "localized_plus_local_gate": _metrics(
                    rows, [local_similarity[i] for i in idx], flags, threshold=selected
                ),
            }
    dest = Path("validation/results/github_event_bge_m3_v0.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "selected_local_threshold": selected,
        "evaluation": {
            split: {variant: {k: v for k, v in metrics.items() if k != "samples"}
                    for variant, metrics in versions.items()}
            for split, versions in report["evaluation"].items()
        },
        "out": str(dest),
    }, indent=2))
    # No false assurance: stop if the small corpus cannot support a candidate.
    if selected is None:
        raise SystemExit("no calibration threshold satisfies declared constraints")


if __name__ == "__main__":
    main()
