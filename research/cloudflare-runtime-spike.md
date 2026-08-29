# Cloudflare Runtime / Cost Spike

**Status:** CAPABILITY/COST SPIKE COMPLETE — live deployment smoke still pending

**Checked:** 2026-08-29

## Question

Can the MVP run mostly on Cloudflare with a very small/free operating footprint without forcing the ML/data architecture into Cloudflare-specific constraints?

## Short answer

**Yes for the public runtime, orchestration, raw/operational storage and a meaningful share of inference. No for heavy clustering / bulk numerical processing on Workers Free.**

Recommended split:

```text
Cloudflare
├── Worker + static assets       public API/UI, auth, status, light routing
├── D1                           jobs, checkpoints, TrendState, compact metadata
├── R2                           raw batches, normalized batches, evidence, candidate vectors
├── Queues                       batch/page-level async work, never one message per Observation
├── Workflows                    network-bound multi-step orchestration
├── Workers AI                   embeddings, rerank, cheap classification/extraction experiments
├── AI Gateway                   model observability, rate limits, cache, fallback/routing
└── Vectorize                    trend/microcluster centroids, not the full Observation corpus

Local PC / VPS
├── heavy clustering / HDBSCAN
├── retrospective backfills and experiments
├── embedding/model benchmarks
├── high-volume per-document ANN when needed
└── distillation / offline batch jobs
```

This preserves `local-first` as an escape hatch while making Cloudflare the default public runtime.

---

## 1. Workers

Official limits (Workers Free, checked 2026-08-29):
- 100,000 requests/day;
- 10 ms CPU/request;
- 128 MB memory;
- 50 subrequests/request;
- 5 Cron Triggers/account;
- 3 MB Worker size.

Source: https://developers.cloudflare.com/workers/platform/limits/

### Verdict

**MVP: YES for edge/API/orchestration. NO for CPU-heavy analytics.**

10 ms CPU is the important constraint. A Worker should not run HDBSCAN, large-scale dedup, bulk vector math or Parquet analytics on the Free plan.

Good Worker jobs:
- validate/request parsing;
- Source Router invocation;
- create/read job status;
- D1/R2 bindings;
- trigger Workflow/Queue;
- call Workers AI;
- return TOP-15 result;
- serve static UI.

---

## 2. D1

Free allocation:
- 5,000,000 rows read/day;
- 100,000 rows written/day;
- 5 GB total account storage;
- max 500 MB per database on Free;
- max 10 databases on Free.

Sources:
- https://developers.cloudflare.com/d1/platform/pricing/
- https://developers.cloudflare.com/d1/platform/limits/

### Verdict

**MVP: YES for operational state; NO for raw corpus.**

Store:
- collection checkpoints/cursors;
- jobs and run status;
- source health;
- TrendState;
- trend score components;
- aggregate counters/time windows;
- representative evidence pointers;
- user/query metadata if needed.

Do not make D1 the warehouse for every raw article/paper/repository body.

---

## 3. R2

Free Standard tier:
- 10 GB-month storage/month;
- 1 million Class A operations/month;
- 10 million Class B operations/month;
- free egress.

Source: https://developers.cloudflare.com/r2/pricing/

R2 object limits are far above MVP needs (object size up to TiB scale).

Source: https://developers.cloudflare.com/r2/platform/limits/

### Verdict

**MVP: STRONG YES.**

Use R2 as cheap append-oriented data plane:

```text
raw/<provider>/<yyyy>/<mm>/<dd>/<batch>.json.gz
normalized/<provider>/<yyyy>/<mm>/<dd>/<batch>.jsonl.gz
candidates/<run>/<batch>.jsonl.gz
evidence/<trend_id>/<artifact>
exports/<run>/top15.json
```

Keep raw data on TTL/lifecycle where possible. Long-term value lives in compact evidence + TrendState, not an infinite raw mirror.

---

## 4. Queues

Workers Free includes 10,000 queue operations/day. A normally delivered message usually costs three operations: write + read + delete.

Therefore a naive design is only roughly **3,333 successfully delivered messages/day** before the free allocation is consumed.

Message size is 128 KB; consumer batch can contain up to 100 messages.

Sources:
- https://developers.cloudflare.com/queues/platform/pricing/
- https://developers.cloudflare.com/queues/platform/limits/

### Verdict

**MVP: YES, but only at batch/page granularity.**

Bad:

```text
1 Observation = 1 queue message
```

Good:

```text
1 source page / R2 batch / collection slice = 1 queue message
```

A Queue message should mostly carry a pointer/manifest, not an entire corpus payload.

---

## 5. Workflows

Free plan currently includes:
- 3,000 Workflow steps/day;
- 1 GB-month persisted Workflow state;
- Free CPU limits still apply: 10 ms compute per step;
- wall-clock waiting/network I/O can be much longer than CPU time.

Sources:
- https://developers.cloudflare.com/workflows/reference/pricing/
- https://developers.cloudflare.com/workflows/reference/limits/

### Verdict

**MVP: YES for orchestration.**

Potential Workflow:

```text
start collection
→ fetch source page
→ write raw batch to R2
→ normalize/light validate
→ optionally call Workers AI
→ write normalized batch
→ update checkpoint
→ trigger next page / finish run
```

Do not use Workflow steps for CPU-heavy clustering.

---

## 6. Workers AI — embeddings

Workers AI free allocation: **10,000 Neurons/day shared across Workers AI usage**.

Current pricing:
- `@cf/baai/bge-m3`: 1,075 neurons / 1M input tokens;
- `@cf/qwen/qwen3-embedding-0.6b`: 1,075 neurons / 1M input tokens;
- both listed around $0.012 / 1M input tokens.

Source: https://developers.cloudflare.com/workers-ai/platform/pricing/

Derived maximum if the full daily free allocation is used only for one of these embedding models:

```text
10,000 / 1,075 × 1,000,000 ≈ 9.30M input tokens/day
```

Illustrative short-record capacity:
- 100 tokens/Observation → ~93k observations/day;
- 150 tokens → ~62k/day;
- 200 tokens → ~46k/day;
- 300 tokens → ~31k/day.

These are quota-envelope estimates, not expected production throughput; the same neuron pool is shared with other Workers AI calls.

Text Embeddings default rate limit is currently 3,000 requests/minute.

Source: https://developers.cloudflare.com/workers-ai/platform/limits/

### Model candidates

`@cf/qwen/qwen3-embedding-0.6b`
- multilingual-capable embedding family;
- 1,024-dimensional vectors;
- long input support relative to classic BGE models.

`@cf/baai/bge-m3`
- multilingual/multifunction embedding model;
- 1,024-dimensional vectors in Cloudflare AI Search configuration.

Sources:
- https://developers.cloudflare.com/ai/models/%40cf/qwen/qwen3-embedding-0.6b/
- https://developers.cloudflare.com/workers-ai/models/bge-m3/
- https://developers.cloudflare.com/ai-search/configuration/models/supported-models/

### Verdict

**MVP: STRONG YES as an EmbeddingProvider candidate.**

Do not lock the project to it yet. Benchmark Cloudflare Qwen3/BGE-M3 against the local candidates using the same evaluation corpus.

---

## 7. Workers AI — reranking

`@cf/baai/bge-reranker-base` currently costs 283 neurons / 1M input tokens.

If the entire free allocation were used only for reranking:

```text
10,000 / 283 × 1,000,000 ≈ 35.3M input tokens/day
```

Source: https://developers.cloudflare.com/workers-ai/platform/pricing/

### Verdict

**MVP: YES for ambiguous relevance/cluster routing after cheap retrieval.**

Use only after candidate narrowing; do not rerank every possible source pair.

---

## 8. Vectorize

Workers Free includes:
- 5 million stored vector dimensions;
- 30 million queried vector dimensions/month.

Source: https://developers.cloudflare.com/vectorize/platform/pricing/

At 1,024 dimensions/vector, the storage cap is only:

```text
5,000,000 / 1,024 ≈ 4,882 vectors
```

At 768 dimensions:

```text
≈ 6,510 vectors
```

Source limits allow much larger indexes technically, but Free billing dimensions are the practical MVP constraint.

Source: https://developers.cloudflare.com/vectorize/platform/limits/

### Critical architecture consequence

**Do NOT store every Observation embedding in Vectorize Free.**

Store only compact semantic state such as:
- TrendState centroids;
- accepted microcluster centroids;
- representative evidence centroids;
- optionally a small active candidate window.

Per-document embeddings can be:
- used ephemerally;
- stored only for unassigned/new candidates in R2;
- clustered offline locally;
- discarded after assignment when provenance/evidence is retained.

This is a good match for the project's original distillation idea.

---

## 9. AI Gateway

Core AI Gateway features are currently free and include analytics, caching and rate limiting. Workers Free has 100,000 persistent logs total across gateways.

AI Gateway also supports retries/fallbacks, spend limits, multiple providers and custom HTTPS providers. Cloudflare now exposes OpenAI-compatible/REST model endpoints and dynamic routing.

Sources:
- https://developers.cloudflare.com/ai-gateway/reference/pricing/
- https://developers.cloudflare.com/ai-gateway/features/
- https://developers.cloudflare.com/ai-gateway/configuration/fallbacks/
- https://developers.cloudflare.com/ai-gateway/configuration/custom-providers/
- https://developers.cloudflare.com/ai-gateway/usage/rest-api/

### Verdict

**MVP: YES for `AnalystProvider` / external model observability and fallback.**

Keep our own provider interface, but let one implementation route through AI Gateway rather than rebuilding analytics, spend caps, retry/fallback and logs ourselves.

Potential later route:

```text
Workers AI cheap model
→ fallback external model
→ final strong analyst model only for finalists
```

---

## 10. R2 Data Catalog / R2 SQL

R2 Data Catalog is a managed Apache Iceberg catalog. R2 SQL can query Parquet-backed Iceberg tables. Current included tiers include 1M catalog operations/month and R2 SQL includes 10 GB scanned/month before usage pricing.

Sources:
- https://developers.cloudflare.com/r2-data-catalog/platform/pricing/
- https://developers.cloudflare.com/r2-sql/platform/pricing/
- https://developers.cloudflare.com/r2-sql/query-data/

### Verdict

**LATER, not first MVP.**

It could eventually replace parts of ad-hoc remote Parquet analysis and integrate well with DuckDB/Iceberg, but it requires an Iceberg/Data Catalog ingestion path. Plain R2 objects are simpler for the first vertical slice.

---

# Proposed MVP runtime v0

```text
Browser/UI
   │
   ▼
Cloudflare Worker
   │
   ├── D1: job/query state
   ├── AI Gateway: final LLM calls / fallback / logs
   │
   ▼
Workflow
   │
   ├── Source Router
   ├── source API fetches
   ├── R2 raw batch
   ├── normalization
   ├── Workers AI embeddings/rerank
   └── R2 normalized/candidate batch
              │
              ▼
       offline/local pipeline
       heavy clustering + validation
              │
        ┌─────┴─────┐
        ▼           ▼
      D1         Vectorize
   TrendState    centroids only
        │           │
        └─────┬─────┘
              ▼
       TOP-15 synthesis
              │
              ▼
          Worker API/UI
```

## Why the local/offline stage remains

Workers Free's 10 ms CPU ceiling is the limiting factor, not network/storage/inference. Keeping the numerical clustering stage replaceable avoids forcing a paid plan or a JavaScript-only ML stack before the methodology is validated.

Later options:
- Workers Paid ($5 minimum) dramatically relaxes CPU limits;
- move clustering to a small VPS;
- run periodic clustering on local PC;
- use an external batch compute provider;
- replace local stage when a Cloudflare-native method proves cheaper/simpler.

---

# Final decision from spike

1. **Cloudflare becomes the preferred public runtime candidate.**
2. **R2 is the main cloud data plane; D1 is compact operational/state storage.**
3. **Workers AI joins the embedding/reranker benchmark as a first-class provider.**
4. **Vectorize stores trend/microcluster centroids, not all document vectors.**
5. **Queues operate on batches/pages, never per Observation.**
6. **AI Gateway should provide model observability/rate limits/fallback instead of custom infrastructure where practical.**
7. **Heavy clustering remains local/VPS for the first vertical slice.**
8. **R2 SQL/Data Catalog is deferred until the core detector works.**
9. A live Cloudflare smoke deployment is still required before closing the deployment validation milestone.
