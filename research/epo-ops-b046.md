# B-046 — EPO OPS adapter, before authenticated access

Status: implemented as a **credential-gated, offline-tested integration**, not a live validated patent feed. Date: 2026-10-09.

## What now exists

- OAuth 2.0 client-credentials request to EPO OPS v3.2 and cached short-lived bearer token.
- Bounded `published-data/search/biblio` CQL query via `X-OPS-Range` (1..25 records/page, at most 20 pages per query).
- Namespaced XML bibliographic mapping to Observation v0.2.0; publication ID includes country, number, and kind code.
- Publication date is taken **only** from publication-reference. Priority/filing dates and ingestion time are never substituted for an unknown publication date.
- Patent family identifiers are preserved where returned. Raw XML can be stored with the existing CollectionRunner before its continuation checkpoint.
- Patent match remains `evidence_type=patent`, not confirmed commercial adoption or verified semantic relevance; no impact on Emerging Score until independent gating.
- Fail closed on missing credentials, bad XML, 401, 429, and incomplete core bibliographic identity.
- Mock-based test suite checks token caching, bounded pagination, schema contract, family, classifications, missing publication dates, error handling and absence of token from normalized observations.

## Execution readiness

Config `config/sources.yaml` is now `0.3.1`, with EPO OPS `execution_status: credentials_missing`. This is **not** a live health check. EPO remains excluded from `collectable_providers` until a verified authenticated smoke and registry update; Hugging Face still lacks an adapter.

EPO credentials must be created at https://developers.epo.org/ and supplied *outside* source control as `EPO_OPS_CONSUMER_KEY` and `EPO_OPS_CONSUMER_SECRET` to an authorized runner.

Manual smoke example (do not print or commit secrets):

```bash
export EPO_OPS_CONSUMER_KEY="..."
export EPO_OPS_CONSUMER_SECRET="..."
python scripts/smoke_epo_ops.py
```

Script performs a single bounded bibliographic query; successful transport alone is **not** evidence of patent relevance, completeness or commercial maturity.

## Deliberate limitations

1. The fixture is synthetic and cannot prove current OPS XML compatibility, API health, rate limits or rights to redistribute patent records. **B-009 remains open** until actual authenticated smoke with an EPO account. The code expects bibliographic XML from the `/search/biblio` constituent.
2. Queries require an explicit bounded CQL string. No arbitrary-direction-to-CQL generator, CPC taxonomy mapping, semantic validator or live incremental schedule was added.
3. Patent family relations are preserved but family-level aggregation, cross-office dedup, validation of relevance and B-035 `research → patent/IP → implementation` remain open. Patent publication normally lags priority/invention.
4. `CollectionRunner` accepts this adapter, but durable actual EPO collection has not run.
5. High-volume/background OPS use is intentionally disabled by default. Follow EPO fair-use limits and usage terms.

Official documentation: https://www.epo.org/en/searching-for-patents/data/web-services/ops

## Next narrow gate

After credentials are provisioned in GitHub Actions as secrets, run the authenticated smoke for 1–2 representative materials/hardware CQL queries; preserve response metadata without secrets. Then inspect patent relevance, time order and family duplicates (B-035) on a small independently reviewed holdout before any patent signal affects scores.
