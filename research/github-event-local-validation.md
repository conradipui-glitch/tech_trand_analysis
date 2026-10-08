# B-039: Event-local GitHub evidence experiment (2026-10-08)

**Status:** experimental method implemented and actually run. NOT yet approved for production scoring or arbitrary technologies.

## Why this exists

The B-034 pilot compared a short Git event with a much longer mutable current repository description. All four LoRA historical candidates scored ~0.39–0.52 versus a historical centroid threshold of 0.82, which caused false negatives. Lowering that universal threshold would also risk false positives.

We now independently test *the technology assertion within a dated Git event*, not its entire release body or current repository description.

## Frozen corpus + reproducibility

- Gold: `validation/github_event_gold_v0.json` (24 cases: 12 positive, 12 negative; 10 labeled calibration and 14 holdout).
- Source classes: 4 real LoRA live-event excerpts from B-034, preregistered RAG/LoRA benchmark events, and transparent **constructed adversarial** negatives/positives.
- Domains: `lora_llm` and `rag` only; all unknown technology families yield `review_required`.
- Local evidence selector: `src/tech_trend_analysis/github_event_local_gate.py`. It rejects LoRa radio, generic mentions, and ungrounded unrelated release lines; retains only a local assertion about implementation in the requested technical context.
- Metrics: `scripts/evaluate_github_event_local.py` + `scripts/evaluate_github_event_embeddings.py`.
- BGE-M3 Action: [run 37824714572](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37824714572), artifact `github-event-bge-benchmark`.

Threshold choice was made on the *calibration split* with the declared rule: highest local BGE similarity-to-direction threshold with **zero calibration FP and at least 80% calibration recall**. This selected **0.425**. Reported holdout below was evaluated at that threshold without further lowering.

| Evaluation | True positives | False positives | False negatives | True negatives | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Calibration: whole event + local lexical gate | 4 | 0 | 1 | 5 | 80.0% |
| Calibration: extracted local assertion + local lexical gate | 4 | 0 | 1 | 5 | 80.0% |
| Holdout: whole event + local lexical gate | 4 | 0 | 3 | 7 | 57.1% |
| Holdout: extracted local assertion + local lexical gate | **6** | **0** | **1** | **7** | **85.7%** |

**Limit:** small author-curated, partly synthetic, not blindly collected. 0/7 false positives is NOT a reliable estimate of production precision. The held-out examples were visible while engineering the rules; this is a regression set rather than an independent blind generalization test. A larger independently collected sample is required.

## Live experiment (real GitHub API + CPU BGE-M3)

The exact LoRA pilot from B-034 was repeated with *explicitly opt-in* `--experimental-event-local-threshold 0.425`. Production centroid threshold remains 0.82. Both combined pilots completed with Actions **success**.

- Previous strict run [37823436080](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37823436080): 6 repositories, 5 histories checked, 4 timestamp-verified events, **0 accepted / 4 rejected**.
- New experimental run [37825141915](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37825141915): same size, 4 events, **2 accepted / 2 rejected**.

| Repository | Verified event | Timestamp | New BGE to direction | Gate outcome |
| --- | --- | --- | ---: | --- |
| `huggingface/peft` | `modules_to_save` to `LoraConfig` | 2023-02-01 | 0.43758 | accepted experimental |
| `hiyouga/LlamaFactory` | release line supporting `--lora_target all` | 2023-09-11 | 0.46334 | accepted experimental |
| `modelscope/ms-swift` | LoRA diffusers image-only bug | 2023-09-19 | 0.29458 | rejected |
| `lyogavin/airllm` | LoRA training Qwen commit | 2026-09-05 | 0.41783 | rejected, below 0.425 |

An accepted event in this pilot is a **dated implementation observation within a small bounded API search** — NOT proof of first-ever implementation, patent, adoption, or globally earliest technology appearance.

An earlier, relevant PEFT commit was independently verified in [B-032](./implementation-transition-validation.md) on **2022-11-30**. The current generic alias search selected a **2023-02-01** commit; earliest-event recall remains a distinct problem. Do not use 2023-02-01 as PEFT's true first-seen date.

## Implementation and rollout safety

- `GitHubBridgePolicy.experimental_event_local_threshold` defaults to **None**. Main production-like bridge still uses conservative same-centroid `0.82`.
- When opt-in is enabled: require event-local technology/implementation context AND real BGE-M3 cosine to the supplied technology direction at the experimental threshold.
- New accepted observations receive `quality_flags.experimental_event_local_gate=true` and the measured `metrics.event_local_similarity_to_direction`.
- No LLM hallucinated dates and no repository `created_at` backdating.
- Model mismatch, missing vector dimension, unknown technology family, no timestamped relevant event all fail closed.
- All results are kept in Actions/local validation artifacts, **not published as TOP-15 or injected into public production scoring**.

## Next gates

1. B-040: bounded **multiple dated events per repository** with chronological event-local selection. A false early lexical match should not block an actually relevant later event. Reproduce PEFT's 2022-11-30 `add lora support` finding.
2. B-041: independent blind external Git event sample across repositories and longer release notes; measure false positives and research→implementation lead times. Avoid choosing a threshold based on one live batch.
3. B-037: avoid double counting repository snapshot + verified event in score. Keep safe weighting of independent actors/evidence.
4. Only after calibration extend event-local rules beyond explicitly evaluated software/AI families.
