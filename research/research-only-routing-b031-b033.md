# B-031 + B-033 — Research-only false positives and source routing audit

Date: 2026-10-09. **Status:** first bounded live/CI audit complete; changes implemented without deploying a dynamic production detector or generating artificial TOP-15 results.

## B-031: keep research visible, but distinguish it from applied emergence

The real OpenAlex v0.4 retrospective already demonstrated a keyword contamination problem: an aggregate search hit before the known research-origin date is not proof that a named technology existed. In the new bounded live sample (Action [37848635222](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37848635222)):

| Month / query | OpenAlex raw matches | Sample reviewed | Accepted as same named research cluster |
| --- | ---: | ---: | ---: |
| Nov 2019, retrieval augmented generation (RAG's May 2020 named paper is later) | 356 | 15 | 0 |
| Dec 2020, low rank adaptation (LoRA's June 2021 named paper is later) | 2,899 | 15 | 0 |
| Jul 2026, agentic AI (research-only sampling) | 25,236 | 15 | 15 |

**Interpretation:** raw counts are search results, NOT cluster-scoped observations and certainly not implementations. Zero accepted in 15 samples is not proof that no conceptual predecessor exists; pre-origin dates are validation reference points, not universal invention dates. A search sorted by relevance is NOT a random sample from the total result set.

The Jul 2026 agentic query exposes the most serious measurement flaw: extrapolating the 15 inspected relevant search records to 25,236 independent source observations would artificially inflate growth, confidence and actor counts. The `SampleGateResult.estimated_count` remains a *diagnostic, statistically unvalidated extrapolation*. A separate `grounded_sample_count` was added: `min(raw_count, matched_sample_count)`. The **active** `scripts/run_retrospective_calibration.py` v0.5 uses only this confirmed sample lower bound in score timelines. It retains raw search counts, sampled indices and extrapolated estimates for inspection. The deprecated historical v0.2/v0.3 scripts must not be used to assert current calibrated scores.

Additionally, research-only `TrendState` instances still score and appear in TOP results, but when there is no independently evidenced patent, implementation, product or adoption they are labelled `weak_signal` rather than `emerging` or `early_adoption`. The assembled trend explicitly warns of missing applied confirmation. This prevents publication popularity from being represented as proven applied technology without suppressing the valuable early scientific watchlist.

A real applied transition can still become `emerging` without requiring a patent for software; research-only is not removed from the ranking. Historical research volumes and implementation dates are not inferred from GitHub repository creation metadata.

## B-033: policy route versus executable collectors

Routing tests and [live configuration run 37848635222](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37848635222) cover the three preregistered technology directions:

| Direction | Classifier | Collectors with installed adapters | Policy-enabled but not collectable |
| --- | --- | --- | --- |
| AI agents | software_ai | GitHub, OpenAlex | Hugging Face (adapter missing), EPO OPS (adapter + credentials missing) |
| Neuromorphic computing | hardware_semiconductor | OpenAlex, GitHub | EPO OPS (adapter + credentials missing), Hugging Face (adapter missing) |
| Solid-state batteries | materials_energy | OpenAlex | EPO OPS (adapter + credentials missing); GitHub and Hugging Face disabled by profile |

The `SourceRouter` now exposes `enabled_providers` (intended domain policy), `collectable_providers` (statically known installed adapters) and `blocked_providers` with `execution_status`. This **does not perform live credentials/network/API-health checks**. Source collection priority still only changes which source to collect first, never Emerging Score weight. Manually overridden profile routing remains available.

`config/sources.yaml` v0.3.0 marks OpenAlex and GitHub adapter implementations ready, Hugging Face adapter missing, EPO OPS adapter and authenticated credentials missing. No API key is committed. Patent evidence is valuable to hardware/materials but is not falsely marked available until the corresponding adapter and credentials exist.

## Gates before public dynamic analysis

1. Confirm v0.5 retrospective result after recalculating from **actually inspected samples**, and separately validate semantic completeness on a larger independent set. Sample-gated ranking is still an *evaluation proxy*, not the production BGE-M3 centroid gate.
2. For arbitrary hardware/materials directions, actually implement/authenticate EPO OPS and evaluate representative research→patent→implementation history (B-035) before claiming full IP coverage.
3. Build the durable dynamic direction→candidate→TOP result pipeline; do not publish partial operator shell snapshots as if arbitrary-direction analysis were implemented.
4. Address source sample selection bias before treating provider aggregate search counts as scientific observation volume.

Validation code: `scripts/validate_routing_research_only.py`, `tests/test_source_router.py`, `tests/test_scoring.py`, `tests/test_result_assembler.py`, `tests/test_history_filter.py`. Retrospective v0.5 Actions workflow stores its JSON as `retrospective-validation-v0.5`.


## Retrospective v0.5 completed (post-fix confirmation)

The full active retrospective was rerun in [GitHub Actions 37849106788](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37849106788), succeeded, and uploaded a real JSON artifact `retrospective-validation-v0.5` (21? no, workflow retention 30 days).

| Case | First matching gated research month | Sustained research month | Useful score signal | Lead to preregistered milestone | Pre-origin gated sampled papers |
| --- | --- | --- | --- | --- | --- |
| RAG | 2020-05 | 2021-01 | 2022-01 | 14 months | 0 |
| LoRA | 2021-06 | not found | not found | not established | 0 |

This is the **recomputed score from inspected accepted samples**, not extrapolated provider totals. The useful-score definition and preregistered milestone dates were unchanged. RAG's target (at least three months lead) still holds **within this research-sample proxy**. LoRA's research-only target is unproven; historically verified implementation evidence is studied separately and cannot be inferred from publication counts. Neither case proves first-ever technological existence, and this limited score validation must not be applied as a blanket promise about arbitrary directions.

The first attempt to publish the v0.5 artifact (run `37848890715`) failed solely due to an outdated `upload-artifact` path; the actual calculation completed. The path was fixed, and run `37849106788` was fully green with `retrospective-validation-v0.5` available.
