# B-044 follow-up: fresh-project Git lineage holdout (2026-10-09)

**Status:** successfully executed as a small diagnostic; production quality gate remains **OPEN**.

## Why this matters

B-043 showed 1/1 positive and 6/6 negatives in Hugging Face TRL. B-044 initially missed PEFT's renamed source module. B-045 fixed the exact PET → PEFT chain and scored 3/3 positive, 8/8 negative in an **11-case targeted regression**, but 9 examples had already been analyzed.

This follow-up checks previously unused **repository groups** with the same frozen B-045 verifier. It does not retune thresholds, add model heuristics, or change scoring.

## Frozen before evaluation

- File: `validation/github_module_lineage_unseen_v4.json` (commit preceding live workflow).
- 8 actual GitHub commits, two groups:
  - `langroid/langroid` — RAG search tool at anchor SHA `151a11fa4c4e7c0107c720b5ffb75982371dfec1`; later in-module enhancement `4a71233775bfbe36f9b7bff50c9994a66551fed9`, removal, unrelated doc-chat module and pre-anchor negative.
  - `OpenRLHF/OpenRLHF` — LoRA code at anchor SHA `fc21f3eae0d161113b59cb056bbc46da98522601`; later LoRA dropout fix in anchored `ppo_actor.py` at `5bf1a7b6f0f951252ef99dd1e1fc97948a32ca10`, LoRA implementation in *other* modules (not maintenance of the anchored one), and an older event.
- Labels represent **verified supporting changes in the SAME already-anchored module**, not whether the technology exists anywhere in the repository. A new LoRA combiner is not the same source-module lineage as a PPO actor.
- Samples were selected and labelled based on public commit messages and changed-file lists prior to running this scoring procedure. This is NOT independent blind expert review nor probabilistically sampled data.

## Real GitHub verification

Workflow: [github-module-lineage-unseen, run 37847283061](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37847283061). It completed successfully, and the raw case decisions were uploaded as `github-module-lineage-unseen`.

| Class | Correct | Incorrect |
| --- | ---: | ---: |
| Supporting module changes | 2 / 2 | 0 |
| Non-supporting changes | 6 / 6 | 0 |
| Total | 8 / 8 | 0 |

Source provenance combines real Git SHA commit metadata, `compare` ancestry, bounded rename lookup where necessary, and actual added lines to the previously confirmed source module. No LLM involved. No `first_seen`, scoring, adoption/actor or trend calculations changed.

## Limitations / remaining gating conditions

1. Eight purposively chosen cases are inadequate to assert population precision/recall. This is a code and boundary check on more varied sources.
2. No genuinely new *multi-hop* source rename from an unfamiliar repository was found and evaluated here; synthetic multi-hop tests and the real PET → PEFT single-hop case remain the only rename-specific evidence.
3. A separate, ideally independently labelled multi-repository corpus with hidden labels and real branch/rename histories is necessary before activating supporting-lineage signals at scale.
4. B-037 protects Emerging Score: **a project remains one independent adoption** even if dozens of historical changes to its code are verified. Do not merge auxiliary maintenance into ranking.
5. Useful product next step is to progress dynamic directions and grounded end-to-end analysis rather than indefinitely expand this auxiliary maintenance subfeature. Keep it available as historical evidence for future trend-detail pages, not as a required condition to present current trends.
