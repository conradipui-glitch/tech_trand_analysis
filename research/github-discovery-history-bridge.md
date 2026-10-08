# B-034 — GitHub discovery → verified history → TrendState

Status: **code + CI integration tests implemented**. Live discovery and live event-history were independently exercised earlier; a single combined production-model live run remains a pilot, not a completed user-facing detector.

## What is implemented

1. `GitHubAdapter` searches bounded, current repository metadata and creates `Observation` with `published_at=null`. Repository `created_at` is metadata, never a technology-origin timestamp.
2. `Microclusterer` groups repository snapshots using one real embedding provider (production default: `BAAI/bge-m3`).
3. `TrendStateManager` owns persistent trend identity; the history pass operates only on repositories **already assigned** to a trend.
4. `GitHubHistoryClient` searches bounded relevant commit/release/tag events. Their own Git event timestamps are used, not repository creation dates; the full event text is retained for embeddings.
5. `GitHubHistoryBridge` gates historical events against the existing **same-model** trend centroid via `gate_historical_vectors()`. Search aliases are NOT appended to semantic input. Rejected events cannot backdate the trend. Accepted events attach to the existing identity using an already-owned repository anchor.
6. `run_github_pipeline()` orchestrates discovery, clustering, TrendState initialization, history verification and history ingest. It returns actual observations, state snapshots and counters, **not a claimed TOP-15**.

Code:
- `src/tech_trend_analysis/github_live_pipeline.py`
- `src/tech_trend_analysis/github_history_bridge.py`
- `src/tech_trend_analysis/sources/github_history.py`
- `scripts/run_github_live_pipeline.py`

## Run locally / on VPS

The full pipeline requires a real, consistent embedding model; there is **no TF-IDF/hash fallback** for timestamp-sensitive history. Optional large model download can take time and disk/RAM.

```bash
python -m pip install -e '.[embeddings]'
export GITHUB_TOKEN='<store this securely; do not commit>'
python scripts/run_github_live_pipeline.py \
  --direction 'retrieval augmented generation' \
  --query 'retrieval augmented generation' \
  --profile software_ai \
  --alias 'retrieval augmented generation' \
  --context 'language model' \
  --limit 10 \
  --max-history-per-cluster 2 \
  --output-dir validation/results/github-live-rag
```

Output: `observations.jsonl`, `trend_states.json`, `summary.json`. Save secrets in CI/provider secret manager, not source control. Avoid treating raw output as a verified TOP-15.

## Provenance and limitations

- Verified means **event text + Git metadata date + semantic gate**, not cryptographically proven first ever use. Git history can be rewritten and API search windows are incomplete.
- Only **one earliest text-matched event per repository** is considered. If an early lexical match fails the semantic gate, this pilot does not search for later semantically valid events. This intentionally prefers false negatives over invented historical evidence.
- The implementation currently counts both a current repository snapshot and a verified event as separate observations. Future scoring must weight/collapse multiple observations representing the same repository/actor so one source cannot amplify an emerging score.
- The present CLI does not persist the TrendState across runs or schedule collection. This is a reproducible local vertical slice, not the finished API job runtime.
- For vague/ambiguous directions, vetted `--alias`, `--context`, `--distinctive` values matter; short acronyms are not historical proof by themselves.
- Work is bounded using `--limit` and `--max-history-per-cluster`. Repository API queries (search + per-repo commit/release/tag) can still consume considerable GitHub rate quota.

## Test evidence

- `tests/test_github_history_bridge.py`: relevant early event, semantic negative, missing event, date/model safeguards, existing trend routing, replay idempotence and JSON schema.
- `tests/test_github_live_pipeline.py`: full data flow via real adapters + mocked HTTP API/embeddings; a lexical GitHub false positive is rejected by the semantic gate. No external GPU/API required for tests.
- Prior live GitHub discovery: 20 repository observations for `AI agents` (workflow `33275313866`).
- Prior live dated RAG/LoRA event benchmark: research → implementation transition (workflow `33275069636`, see `research/implementation-transition-validation.md`).
- Combined **live BGE-M3** pipeline still needs an explicitly budgeted pilot before claiming end-to-end operational validation.

## Next gate

One bounded combined live pilot using the same embedding model (`BAAI/bge-m3`) on 5–10 repositories; inspect accepted/rejected matches manually, verify temporal chronology and source/actor dedup policy before letting results affect TOP-15 ranking.


## 2026-10-08 live CPU/BGE-M3 calibration findings

**Actual pipeline execution succeeded** in GitHub Actions, with no paid model API.

- Run `37822672120`, RAG: six present-day repositories, two microclusters, two repositories checked, **zero text-verified events**. Sorting by `updated` overrepresented new 2025–2026 repos. This is discovery bias, not evidence that no older implementations exist.
- Run `37823051497`, LoRA: six well-known repositories, five microclusters, five repositories checked, **four text-verified dated events, zero accepted** by `gate_historical_vectors()`.
- Run `37823436080` reproduced LoRA findings with evidence text, URLs, cosine and decisions saved as `history_checks.json` (Actions artifact `github-live-lora-audit`).
- All regular Python integration/unit CI checks remained green. This proves execution and fail-closed behavior, not detector usefulness.

Observed real BGE-M3 cosine values with **existing repository-desc-based centroid** and **Git event text**:

| Repository | Event / interpretation | Event timestamp | Cosine | Decision |
| --- | --- | --- | ---: | --- |
| `modelscope/ms-swift` | `Fix bug: LoRA not work with diffusers>0.20.0` — image/diffusers context | 2023-09-19 | 0.39152 | reject |
| `lyogavin/airllm` | `streamed LoRA training for Qwen3.8` — likely relevant to LLM LoRA | 2026-09-05 | 0.49934 | reject |
| `huggingface/peft` | `modules_to_save to LoraConfig` — relevant | 2023-02-01 | 0.48354 | reject |
| `hiyouga/LlamaFactory` | `FlashAttention-2 and Baichuan2` release — likely adjacent, not a LoRA-introduction event | 2023-09-11 | 0.51946 | reject |

**Implication:** the `0.82` centroid similarity threshold was developed for same-style history and is NOT validated for cross-modal repository-description ↔ Git-message pairs. Merely lowering it below 0.5 would accept some relevant evidence *and* risk accepting off-topic release evidence, as seen above. Do not tune on these four samples alone.

**Next calibration gate:** freeze a labeled multi-repository event corpus (commit, release, tag, including ambiguous `LoRA` vs `LoRa` and unrelated changelog mentions); evaluate event-local evidence snippets and cross-modal embedding criteria separately from the same-style OpenAlex centroid gate. Preserve event links/dated provenance and require explicit false-positive performance before injecting these events into score. One lexical-history miss was also observed: generic `LoRA` context did not rediscover PEFT's known earlier `add lora support` commit (2022-11-30); repository-specific safe contextual query policy needs testing before claiming earliest implementation.

**Status after pilot:** bridge code is complete and reproducibly exercised. It has not yet produced a trustworthy, chronologically enriched **live** TrendState from arbitrary discovery. Therefore this is still a validation-stage pipeline, not a completed TOP-15 service.
