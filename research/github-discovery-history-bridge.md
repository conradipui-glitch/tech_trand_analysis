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
