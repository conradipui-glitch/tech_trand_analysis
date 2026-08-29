# Data Contracts

## Purpose

The project has two stable boundaries:

1. **Provider adapter → `Observation`**
2. **Trend engine → `TrendAnalysisResult`**

Everything outside these boundaries may evolve independently as long as the contracts remain valid.

Schemas:
- `schemas/observation.schema.json`
- `schemas/trend-result.schema.json`

Current contract version: **0.2.0**.

## Observation contract

`Observation` is one normalized evidence item. A GitHub repository, patent, paper, model, report or future provider record must become the same outer object before entering deduplication, embeddings, clustering or scoring.

### Stable vs extensible fields

**Stable semantic taxonomy:**
- `evidence_type`

Allowed values are deliberately small: `research`, `patent`, `implementation`, `product`, `adoption`, `investment`, `regulation`, `analysis`, `other`.

The trend engine may assign weights to these values, therefore a provider must map its records into this shared taxonomy.

**Extensible without core schema changes:**
- `provider`
- `artifact_kind`
- actor `kind`
- relationship `type`
- provider-specific keys inside `metrics`

This is intentional. Adding a new source must not require editing the central schema merely because a new website/API appeared.

### Field ownership

The adapter owns:
- provider/external identity;
- canonical URL;
- title and compact source text;
- source dates;
- actors;
- provider-native topics/classifications;
- raw provider metrics;
- relationships known directly from the provider;
- provenance and optional raw pointer.

The adapter **must not invent downstream analysis**. `analysis.relevance`, `analysis.novelty`, `cluster_id`, embeddings and technology labels are populated by later pipeline stages.

### Time rules

- `observed_at` is our ingestion timestamp and must be an ISO date-time.
- `published_at` / `updated_at` may be either a full date or date-time because providers differ in precision.

### IDs

Recommended form:

```text
observation_id = <provider>:<stable external identity>
```

Examples:
- `github:vercel-labs/agent-browser`
- `openalex:W123...`
- `epo_ops:EP...`

The exact encoding may vary, but it must be deterministic and stable enough for incremental deduplication.

### Raw data and secrets

`raw_ref` may point to R2/local temporary raw data. It must never contain credentials, API tokens or signed secrets.

`rights` stores only informational access/reuse metadata and is not a legal determination.

## TrendAnalysisResult contract

The service request is fixed to a requested limit of **15** trends.

The system is allowed to return fewer than 15 only when evidence is insufficient or source coverage is degraded. It must never fabricate weak trends merely to fill the list.

### Result status

- `ok` — sufficient evidence and normal source coverage;
- `partial` — usable result, but fewer trends and/or reduced provider coverage;
- `insufficient_evidence` — the requested direction cannot be supported reliably.

### Transparency requirements

The response includes:
- providers actually used;
- attempted/succeeded/failed source coverage;
- observation/candidate counts;
- warnings;
- score and confidence separately;
- every score component;
- first-seen method and confidence;
- evidence composition;
- temporal trajectory;
- representative sources;
- case example;
- methodology explanation and limitations.

### Score vs confidence

`score.total` answers: **how emerging is the candidate according to the methodology?**

`score.confidence` answers: **how much evidence do we have to trust that score?**

A high emerging score with weak evidence should therefore have low confidence rather than being silently treated as a strong finding.

### Score components

All v0.2 result records must expose:
- growth;
- acceleration;
- novelty;
- recency;
- evidence diversity;
- actor diversity;
- persistence;
- maturity penalty.

The formula/weights belong to methodology versioning, not to the transport schema.

## Contract tests

Fixtures live in `schemas/examples/`.

Run:

```bash
python -m pip install -r requirements-dev.txt
python tests/test_contracts.py
```

The test suite explicitly checks that a completely new `provider` and `artifact_kind` can validate without changing the core schema while an unknown `evidence_type` is rejected.

## Versioning rule

Until the service reaches schema `1.0.0`, incompatible contract changes bump the minor version (`0.2` → `0.3`). Compatible optional additions may bump patch/minor as appropriate.

Every adapter and service response must emit `schema_version`; pipeline stages must fail clearly on unsupported versions rather than guessing.
