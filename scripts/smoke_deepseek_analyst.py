from __future__ import annotations

import json
import os
from pathlib import Path

from tech_trend_analysis.analyst import DeepSeekAnalyst


def main() -> None:
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise SystemExit("DEEPSEEK_API_KEY is not configured")

    trend = {
        "trend_id": "validation-rag",
        "label": "Retrieval-Augmented Generation (RAG) — retrospective diagnostic",
        "profile": "software_ai",
        "stage": "validation",
        "score": {"total": 51.3, "confidence": 0.867, "version": "0.1.0"},
        "metrics": {
            "origin_date": "2020-05-22",
            "ecosystem_milestone_date": "2023-03-23",
            "pre_origin_keyword_matches": 7369,
            "diagnostic": "Broad keyword retrieval produced substantial activity before the preregistered origin, so the historical curve is contaminated and must not be treated as valid early detection.",
        },
        "evidence": [
            {
                "observation_id": "rag-origin-paper",
                "evidence_type": "research",
                "url": "https://arxiv.org/abs/2005.11401",
                "title": "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            },
            {
                "observation_id": "rag-ecosystem-proxy",
                "evidence_type": "implementation",
                "url": "https://github.com/openai/chatgpt-retrieval-plugin",
                "title": "openai/chatgpt-retrieval-plugin repository creation",
            },
        ],
    }

    narrative = DeepSeekAnalyst(api_key=api_key).enrich(trend)
    result = {"ok": True, "trend_id": trend["trend_id"], "narrative": narrative.to_dict()}
    output = Path("validation/results/deepseek-analyst-smoke.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
