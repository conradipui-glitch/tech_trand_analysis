#!/usr/bin/env python3
"""B-041 fixed-threshold evaluation on new, frozen real Git commits.

No parameter fitting. Labels frozen in validation/github_event_external_v1.json.
Does not claim independent blind human annotation.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

from tech_trend_analysis.github_event_local_gate import evaluate_event_local


def score(rows, expected_key="expected"):
    tp=fp=tn=fn=0
    for row in rows:
        expected=bool(row[expected_key])
        prediction=bool(row["predicted"])
        if expected and prediction: tp+=1
        elif prediction: fp+=1
        elif expected: fn+=1
        else: tn+=1
    return {"count":len(rows),"tp":tp,"fp":fp,"tn":tn,"fn":fn,
            "precision":tp/(tp+fp) if tp+fp else None,
            "recall":tp/(tp+fn) if tp+fn else None,
            "false_positive_rate":fp/(fp+tn) if fp+tn else None}


def main():
    data=json.loads(Path("validation/github_event_external_v1.json").read_text(encoding="utf-8"))
    cases=data["cases"]
    decisions=[evaluate_event_local(
        technology_direction=data["directions"][r["direction"]],
        title=r["title"],text=r["text"],
    ) for r in cases]
    texts=[decision.evidence_span or r["title"] for decision,r in zip(decisions,cases,strict=True)]
    inputs=[data["directions"][r["direction"]] for r in cases]+texts
    model=SentenceTransformer("BAAI/bge-m3")
    emb=np.asarray(model.encode(inputs,normalize_embeddings=True,show_progress_bar=False),dtype=np.float32)
    n=len(cases)
    scores=np.sum(emb[:n]*emb[n:],axis=1)
    report=[]
    for r,d,cosine in zip(cases,decisions,scores,strict=True):
        cosine=float(cosine)
        report.append({
            "id":r["id"],"repository":r["repository"],"sha":r["sha"],
            "url":r["url"],"date":r["date"],"title":r["title"],
            "expected":r["expected"],"local_status":d.status,
            "local_reason":d.reason,"evidence_span":d.evidence_span,
            "similarity":round(cosine,5),
            "local_predicted":d.eligible,
            "predicted":d.eligible and cosine>=0.425,
        })
    local_metrics=score([{**r,"predicted":r["local_predicted"]} for r in report])
    combined=score(report)
    result={
        "version":data["version"],"model":"BAAI/bge-m3",
        "threshold":0.425,"threshold_fitted_on_this_dataset":False,
        "local_only_metrics":local_metrics,"combined_metrics":combined,
        "limitations":data["selection_limitations"],"cases":report,
    }
    out=Path("validation/results/github_external_bge_v1.json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"local_only":local_metrics,"combined":combined,
                      "wrong":[{"id":r["id"],"expected":r["expected"],
                                "predicted":r["predicted"],"status":r["local_status"],
                                "cosine":r["similarity"]}
                               for r in report if r["expected"]!=r["predicted"]]},
                     ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()
