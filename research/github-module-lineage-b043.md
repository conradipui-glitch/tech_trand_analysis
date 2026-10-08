# B-043 — Supporting module lineage (2026-10-09)

Status: implementation + initial live sanity pilot complete; NOT production scoring evidence.

## Problem and solution

A short bugfix in an already verified technological module can show continued development without naming the technology. However, repository name, file path, a timestamp or generic text are not proof of a new technology or a new independent adopter.

The new GitModuleLineageVerifier (src/tech_trend_analysis/github_module_lineage.py) requires:
- A *previously confirmed* dated LoRA/RAG Git commit with separately fetched same-SHA executable code evidence;
- Same repository, strictly later dated commit and a different SHA;
- GitHub compare endpoint confirming ancestry (status ahead), not just timestamps;
- Exact same confirmed source file or explicit GitHub rename metadata, changed executable added code;
- On generic shared files (such as utils.py), LoRA/PEFT/adapter or RAG/retrieval/vector code terms in *added executable lines*, not only in filenames;
- No docs/test/example changes, removed-only or comment-only patches.

It returns supporting/rejected/review_required with source paths and dates. It **never** updates first_seen, TrendState, actor counts, Emerging Score or public TOP-15.

## Frozen real GitHub/BGE-M3 pilot

The 7-case labeled set was committed in validation/github_module_lineage_v1.json **before** scoring: 1 positive and 6 negatives.

Anchor: huggingface/trl, LoRA implementation commit b60ce797d8eed012323a83411335399f9f5338de, dated **2024-08-06T16:02:59Z**. Model similarity to LoRA/LLM direction was **0.51906**, above experimental (not production) 0.425.

Positive: dated commit 375b3ebc85fd75f25fcadb74b37057040ef344c7, **2025-11-21T00:42:45Z**, adds target_parameters to LoraConfig in the already verified LoRA code path, GitHub confirmed descendant.

Negatives: unrelated vLLM, dtype/device settings and model-id fallback edits to the same shared utils.py file, docs-only earlier change, anchor self-repeat and different repository.

Run: https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37833921153
Artifact: github-module-lineage-v1 (timestamp, source paths, decisions).

Results: TP **1**, TN **6**, FP **0**, FN **0**. This is **not evidence of 100% population precision or recall**: one-repository, seven deliberately selected cases, no independent blinded annotation. Unit/CI tests cover chronology, ancestry, explicit rename, spoofed paths, comments/docs, shared utils module, replay and source integrity; CI green.

## Next quality gates

- Independently collect labeled **multiple-repository** supporting/non-supporting cases; preserve previously frozen labels, including renames, cross-branch history, LoRA/LoRa and RAG docs-only examples.
- B-037: prevent counting repository snapshots and commits/maintenance as multiple independent actors.
- Keep supporting activity separate from emergence timing and rankings until the policy has real external validation.

## Future interface

Product brief saved to docs/12_PRODUCT_UI_ROADMAP.md; the user-provided Frontend Studio package informs future B-053 work. The actual authored skill files were **not** republished into this public repository.
