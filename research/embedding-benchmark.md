# Embedding Benchmark

**Status:** HARNESS READY — MODEL RUNS PENDING

## Goal

Выбрать embedding model для local-first MVP на собственном technological corpus, а не по публичному leaderboard.

## Candidate models

Primary candidates:
- Qwen3-Embedding-0.6B
- BGE-M3

Execution modes to compare where available:
- local CPU/GPU;
- Cloudflare Workers AI.

## Gold corpus v0

Location: `evaluation/`.

Composition:
- 48 curated passages;
- 12 technology clusters;
- 3 source profiles: `software_ai`, `hardware_semiconductor`, `materials_energy`;
- English + Russian coverage;
- 24 bilingual retrieval queries;
- explicit relevant documents and hard negatives;
- 24 pair cases for same-technology vs adjacent-distinct ordering.

The corpus is deliberately curated rather than scraped: benchmark labels must be known before model scoring. A separate live-Observation validation set will be added after model selection.

## Implemented benchmark metrics

`src/tech_trend_analysis/evaluation/benchmark.py` provides a provider-agnostic embedding contract and calculates:

1. Recall@1
2. Recall@3
3. Recall@5
4. MRR
5. RU MRR
6. EN MRR
7. hard-negative win rate
8. pair-ordering accuracy
9. vector dimension
10. end-to-end embedding runtime

CI validates the benchmark math with an oracle embedding provider; the harness itself is not a model-quality result.

## Operating metrics to collect during real runs

For every provider/model execution also record:
- model identifier/version;
- device / endpoint;
- batch size;
- precision / quantization;
- peak RAM / VRAM when measurable;
- input item count and approximate tokens;
- elapsed time;
- vectors/second;
- vector dimension;
- serialized bytes/vector (float32 and intended storage format);
- API/neuron cost where applicable;
- errors/retries.

## Decision rule v0

Quality gates before cost optimization:
- MRR should be close to 1.0 on this small curated set;
- pair-ordering accuracy should strongly prefer same-technology over adjacent-distinct pairs;
- Russian queries must retrieve English documents from the correct cluster, not only the Russian paraphrase;
- hard negatives must not systematically outrank relevant items.

If models are near-tied on quality, select by operating cost, latency, memory footprint and deployment simplicity.

Do not move to production clustering with a model that only looks good on English queries.

## Next execution

1. Run Qwen3-Embedding-0.6B on the complete v0 corpus.
2. Run BGE-M3 with identical corpus and metrics.
3. Compare local vs Workers AI implementation if both are available.
4. Select one primary `EmbeddingProvider` and optionally one fallback.
5. Freeze benchmark result in this file and then start B-016 clustering.
