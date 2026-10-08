# B-044 — external Git module-lineage comparison

**Outcome:** multi-repository live validation executed; **quality gate remains open**, because one known positive is missed. Do not use supporting events as independent adoptions or for Emerging Score.

## Pre-frozen evidence and run

- Gold: `validation/github_module_lineage_crossrepo_v2.json` (three repository groups, nine actual Git commit pairs, three positive/six negative); labels saved before execution.
- Projects: `huggingface/trl`, `tloen/alpaca-lora`, `huggingface/peft`.
- Action: [github-module-lineage-crossrepo / 37834866820](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37834866820). Job success means the script ran; it does not mean the quality gate passed. Full JSON audit is in the Actions artifact `github-module-lineage-crossrepo`.
- Verification: GitHub individual SHA commit details + real compare status `ahead`, overlapping source module path or explicit same-commit rename, actual added executable lines, chronology.

| Result | Count |
| --- | ---: |
| True positives | 2 |
| True negatives | 6 |
| False negatives | **1** |
| False positives | 0 |

The false negative is `huggingface/peft` commit `d04f6661eec9dc2811cabe6c4405e64a9d49a07f` (2023-02-01), which really extends LoRA configuration; however, the anchored 2022-11-30 module was under `src/pet/tuners/lora.py` and the later module is under `src/peft/tuners/lora.py`. The verifier does **not** infer a multi-commit rename from similar filenames. This conservative rejection is preferable to inventing source ancestry.

Existing unit coverage includes single-commit GitHub-declared rename, branch divergence, docs-only patches, cross-repository evidence, and older-than-anchor rejection. **Live coverage of an actual multi-commit rename and LoRa radio negative is not yet complete**; this pilot is not a blinded randomized sample.

**Next gate:** verify the intervening GitHub file rename chain via commit ancestry and immutable per-SHA rename status, with a strict bound on API lookups. Never infer time of adoption from a path similarity or count a change as a new project.

## Relation to B-037

B-037 is a separate scoring fix: independent GitHub repository units must not count each technical commit as a new trend adopter. The raw event list remains inspectable; supporting-module results never enter scoring.

The next technical priority after B-037 is collecting a more diverse and independently reviewed sample for the remaining B-044 limitations, **not** silently loosening the gate.
