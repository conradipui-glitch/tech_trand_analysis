# Evaluation Corpus v0

Purpose: provide a small, deterministic, human-curated gold set for the first embedding and clustering benchmark.

This corpus is intentionally **not** a dump of live source results. Raw source data contains unknown noise and weak labels; the benchmark needs examples where the expected semantic relation is known in advance. Live Observation validation is a separate stage.

## Scope

Profiles:
- `software_ai`
- `hardware_semiconductor`
- `materials_energy`

Technology clusters (12 total):
- browser agents
- coding agents
- agent memory
- on-device agents
- neuromorphic / spiking processors
- photonic AI accelerators
- compute-in-memory
- chiplet interconnect
- solid-state batteries
- sodium-ion batteries
- silicon anodes
- perovskite-silicon tandem photovoltaics

Files:
- `embedding_corpus.jsonl` — 48 labeled passages, 4 per technology cluster; English + Russian coverage.
- `retrieval_queries.jsonl` — 24 queries (EN/RU), relevant document IDs and explicit hard negatives.
- `pair_cases.jsonl` — 24 pairwise semantic cases: same technology vs adjacent-but-distinct technology.

## What B-015 must measure

At minimum:
1. Recall@1 / Recall@3 / Recall@5 on `retrieval_queries.jsonl`.
2. MRR.
3. Cross-language retrieval: RU query → mixed RU/EN relevant documents.
4. Hard-negative error rate.
5. Pair ordering accuracy: same-technology pair should score above its corresponding adjacent-distinct pair.
6. Runtime, RAM/VRAM, vector dimension and serialized storage cost.

## Rules

- Do not tune model-specific thresholds on the whole set and then report the same set as unbiased evaluation.
- v0 is small enough for model selection, not for a scientific claim about general embedding quality.
- After selecting a candidate model, add a second `live-observations` validation set sampled from real OpenAlex/GitHub/HF/EPO observations.
- Do not silently rewrite labels after seeing model scores; label changes need an explicit review note.
