# Embedding Benchmark

**Status:** COMPLETE FOR B-015

## Goal

Выбрать embedding model для detector core на собственном RU/EN technological corpus, а не по публичному leaderboard.

## Gold corpus v0

Location: `evaluation/`.

- 48 curated passages;
- 12 technology clusters;
- 3 profiles: `software_ai`, `hardware_semiconductor`, `materials_energy`;
- English + Russian;
- 24 bilingual retrieval queries;
- explicit relevant documents and hard negatives;
- 24 pair cases: same-technology vs adjacent-distinct.

## Execution

Reproducible CPU benchmark executed in GitHub Actions run `33265970136` with `sentence-transformers`, batch size 16.

Raw persisted results:
- `research/benchmark-results/qwen3-embedding-0.6b.json`
- `research/benchmark-results/bge-m3.json`

| Metric | Qwen3-Embedding-0.6B | BGE-M3 |
|---|---:|---:|
| Dimension | 1024 | 1024 |
| Recall@1 | 0.2500 | 0.2500 |
| Recall@3 | **0.7396** | 0.6979 |
| Recall@5 | **0.9583** | 0.8854 |
| MRR | 1.0000 | 1.0000 |
| Hard-negative win rate | 1.0000 | 1.0000 |
| Pair-ordering accuracy | 0.6667 | **1.0000** |
| RU MRR | 1.0000 | 1.0000 |
| EN MRR | 1.0000 | 1.0000 |
| Encode time, 72 texts, CPU | 17.96 s | **7.07 s** |
| Model load time | **8.38 s** | 24.27 s |
| Peak RSS | 4244 MB | **2852 MB** |
| float32 bytes/vector | 4096 | 4096 |

`Recall@1 = 0.25` is expected for a perfect ranking under this metric because every query has four relevant documents; top-1 can recover at most one of four. MRR=1.0 means every query ranked at least one relevant document first.

## Interpretation

### Retrieval

Qwen3 retrieves more members of the same technology cluster inside top-3/top-5. Both models place a relevant item at rank 1 for every EN and RU query in v0.

### Clustering geometry

BGE-M3 is materially stronger on the pair-ordering test: all 12 same-technology EN↔RU pairs score above their explicit adjacent-technology hard negatives. Qwen3 succeeds on 8/12.

This matters more for detector clustering than query retrieval because the core task is document↔document semantic geometry across mixed-language evidence, not only query↔document search.

### Runtime

On the GitHub CPU runner BGE-M3 encoded the benchmark corpus about 2.5× faster and used substantially less peak resident memory, although its initial model load was slower.

These timings are environment-specific and are not treated as universal hardware benchmarks.

## Decision

**Primary EmbeddingProvider v0 for clustering: `BAAI/bge-m3`.**

Reason:
- perfect hard-negative and cross-language pair ordering on project corpus;
- lower CPU memory footprint in the measured run;
- faster batch encoding in the measured run;
- 1024 dimensions fit the existing Vectorize centroid budget assumptions.

**Qwen3-Embedding-0.6B remains a strong retrieval candidate/fallback**, because it achieved higher Recall@3/5. Do not remove the provider abstraction or bake BGE-specific behavior into clustering.

## Limitations

- corpus v0 is small and curated;
- pair cases intentionally stress RU↔EN same-technology similarity;
- only CPU GitHub runner measured here;
- Workers AI version/implementation still needs a separate smoke if we want Cloudflare inference in production;
- before production freeze, validate BGE-M3 on a second set sampled from live Observations.

## Next

Proceed to **B-016 clustering prototype** using BGE-M3 as the default embedding geometry and keep model identity/config explicit in cluster metadata.
