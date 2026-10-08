# B-045 — Git module rename chain across dated commits

Status: **bounded implementation and live regression diagnostic green**. This is a supporting source-lineage capability only, not approval for Emerging Score or proof of broad detector quality.

## Observed missed case and verified bridge

Earlier B-044 rejected the PEFT LoRA configuration improvement in commit [d04f666](https://github.com/huggingface/peft/commit/d04f6661eec9dc2811cabe6c4405e64a9d49a07f) on **2023-02-01**, because its source module did not have exactly the same path as the verified implementation [e816037](https://github.com/huggingface/peft/commit/e8160370247b3b61f57e59eb3f49acf9e3618b4b) on **2022-11-30**.

Direct GitHub commit API inspection establishes a concrete, intermediate move:

- Dated commit [086b329](https://github.com/huggingface/peft/commit/086b329c1ae3cd8598c5b6d74093c737f0d0d8d8), **2023-01-15T13:39:56Z**, `addressing comments and renaming pet to peft`.
- Its actual GitHub `files[]` entry contains `status = "renamed"`, `previous_filename = "src/pet/tuners/lora.py"`, `filename = "src/peft/tuners/lora.py"`.
- Both ancestry edges must be proven using GitHub `compare`: anchor → rename and rename → candidate. A date or similar path name alone is insufficient.

## Implementation

- `src/tech_trend_analysis/github_rename_lineage.py`: bounded immutable rename history resolver. It follows exact-path GitHub commit lists, reads dated commit details with `status=renamed` and exact previous filename, verifies both graph directions, follows up to three hops by default, caps history-window length and commit-detail lookups.
- The candidate's actual changed-file names prioritize **search order only**, never serve as rename proof.
- The search terminates as soon as a fully verified path is present in the candidate's same-SHA changed files. No guessing across unrelated source renames.
- Truncated history, exhausted budget, non-ancestral branches and absence of a GitHub-declared rename all **fail closed**. The existing executable same-module change rule still applies even after proving a path rename.
- `src/tech_trend_analysis/github_module_lineage.py` records verified rename hops in `SupportingChangeResult.verified_renames`; it still NEVER changes `TrendState`, `first_seen`, actor counts, score or public snapshots.

## Tests and real GitHub experiment

- Synthetic unit/regression tests: `tests/test_github_rename_lineage.py` with 1-hop and 2-hop renames, missing `renamed` status, unrelated branch, comment-only candidate, truncation fail-closed. Full Python test workflow green.
- Frozen `validation/github_module_lineage_rename_v3.json` committed **before** live evaluation: nine previously assessed B-044 pairs from three repositories plus two new LoRa-radio negatives from `jgromes/RadioLib` and `Lora-net/LoRaMac-node`. Total **11 cases** (3 positives, 8 negatives).
- Real GitHub Actions [run 37844860210](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37844860210) **succeeded** and printed **TP 3, FN 0, TN 8, FP 0**. Full SHA-level decisions, source paths and intermediate rename proofs were uploaded as artifact `github-module-lineage-rename-v3`.
- The earlier B-044 pilot was TP 2 / FN 1 / TN 6 / FP 0. The previously missed PEFT migration is now accepted; two added LoRa-radio cases were rejected.

## Limits and next gate

These numbers are a **targeted regression demonstration**, not a blind independent prospective test. Nine cases were already studied and two new cases are narrow negative controls. The quality gate in B-044 remains open pending a larger independently reviewed multi-repository sample, ideally including actual multi-hop rename chains, unrelated changed-file paths, branch merges and renamed-but-nontechnology files.

No scoring integration is authorized by B-045. B-037 independent-project scoring remains active and unaffected; supporting maintenance still represents auxiliary provenance rather than another adoption.

Do not treat a clean CI run or 0/8 false positives as a population-wide precision estimate.
