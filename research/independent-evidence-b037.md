# B-037 — Independent evidence policy in Emerging Score v0.2

Status: implemented in scoring code, regression tests; preserve raw audit and suppress artificial GitHub volume. This is an accounting/provenance fix, **not independent validation of event semantic quality**.

## Problem

One GitHub repository discovery snapshot (mutable current description; observed now) and its multiple timestamp-verified historical commits were counted as separate `Observation` entries, so monthly growth, evidence volume, confidence and maturity could be falsely amplified.

## Rule (scoring only)

- Group any GitHub repository and commit/release observations which contain the same normalized **owner/repository** identity as **one independent implementation unit**.
- If the group has a verified historical event (actual Git-event timestamp), use its **earliest verified date** as the group's effective score timestamp. Otherwise count its present-day discovery at `observed_at`. **Never infer technology origin from `repo.created_at`**.
- A later commit from the same repository **does not increase** the number of independent units, effective monthly count, actor diversity, confidence or growth. It remains in raw Observation evidence for provenance.
- Two distinct repositories (even under one GitHub owner) remain two implementation units but count as **one independent GitHub owner/actor**, so actor diversity cannot inflate by repeated commits.
- Different OpenAlex papers and other non-GitHub observations remain independent unless deduplicated upstream; no new cross-provider person/company entity resolution is claimed.
- Supporting maintenance discovered by B-043/B-044 is **not** fed to the scoring index as a new adoption.
- Unverified Git commit metadata cannot backdate scoring history: use `observed_at` until the history event is actually verified.
- Missing `belongs_to_repository` for a GitHub event fails closed before changing TrendState counters; replay preserves identity and score.
- Legacy GitHub TrendStates with raw IDs but **no independent-unit index** fail closed and must be re-ingested from original Observations to avoid silent inflated scoring.

## Implementation

`src/tech_trend_analysis/independent_evidence.py`: `IndependentEvidenceUnit` and deterministic representative selection; verified earlier event beats a current snapshot, then earlier verified event beats later verified event.

`TrendStateManager` keeps original `observation_ids`, raw by-month/provider/evidence counters and adds `independent_units` for the score view; export includes version and provenance.

`EmergingScorer` v**0.2.0** builds a temporary projected TrendState: independent-unit event dates, evidence/provider/actor counts and monthly buckets; the original state remains unchanged. Existing score weights and mathematical components are unmodified. Pure historic tests/manually constructed non-GitHub states without units use the previous aggregate values for compatibility.

## Test acceptance

`tests/test_independent_evidence_scoring.py`: raw count increases when new Git commits arrive, **score total, confidence and stage remain identical**; earliest real event replaces current discovery for monthly score, independent repositories increase evidence but not same-owner actor diversity, unrelated papers are still distinct, orphan events fail prior to mutation, unverified event cannot backdate score, repeated collection idempotent.

## Limitations and future review

This policy counts unique **GitHub projects**, not directly true market companies or adopters. Forks may also need special weighting; a full actor identity resolution across OpenAlex/GitHub/patent registries is outside B-037. Historical maintenance is intentionally ignored for *volume* signals; it may later be displayed as a separate, clearly labelled development-activity timeline only after validation.

Score v0.2 is a methodological accounting change. Compare historical benchmarks run with score v0.1 and v0.2 **only** after replaying the same evidence under both rules. No public Cloudflare TOP-15 was regenerated in this task.
