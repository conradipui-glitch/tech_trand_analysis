# B-040/B-041 — chronological Git evidence and external validation

State: B-040 completed as bounded code and real PEFT-history pilot; B-041 **evaluated but fails recall quality gate**. Neither experimental Git history enrichment nor B-039 threshold should enter production Emerging Score yet.

## B-040: earlier real PEFT event recovered

- GitHub Actions live CPU BGE-M3 run: [37827493215](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37827493215), artifact `github-chronology-peft`.
- Source: `huggingface/peft` candidate search, aliases `LoRA`, `lora`, `low rank adaptation`; chronological bounded GitHub API search, max 30 candidates, max two pages per term, max nine actual commit patch inspections.
- Results: **30 candidates**, six locally eligible and above experimental cosine threshold 0.425. Earliest accepted dated event was commit `e8160370247b3b61f57e59eb3f49acf9e3618b4b` on **2022-11-30T09:21:26Z** (message `add lora support`).
- BGE-M3 event-to-direction similarity for earliest accepted: **0.51376**.
- Proof: the commit itself changes `src/pet/tuners/lora.py`, adds `LoRAConfig`/`LoRAModel` and `loralib` references. This is same-SHA code evidence, not a mutable repository description.
- The older path had selected `modules_to_save to LoraConfig` in February 2023. The earliest *accepted within bounded search* moved back to November 2022. This is **not a claim of globally first LoRA implementation**, and the bounded search need not cover every Git event.

Implementation:
- `GitHubHistoryClient.candidate_events()` retrieves multiple bounded commit/release candidates, de-dups aliases, sorts by event timestamp, and enriches up to a bounded number of short commits with actual added source-code lines from the same SHA.
- Git diff snippets ignore removed lines and comment-only changes; neither `repo.created_at` nor mutable current description may prove implementation.
- `GitHubHistoryBridge`, only in explicit **experimental** mode, selects the earliest event that passes event-local checks and BGE similarity for each already-owned repository. Later eligible events do not duplicate the same repository's count. Default production-like threshold 0.82 is unchanged.
- Lightweight tags **cannot be backdated to the referenced commit**. They are excluded until an annotated tagger timestamp implementation is validated. Published releases require actual `published_at`.
- Tests include LoRa radio before LoRA code, same-SHA patch, later eligible candidates, no bogus early dates, replay/idempotency. Last relevant unittest CI green: [37827588853](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37827588853).

## B-041: new Git repositories, frozen BEFORE scoring

Gold dataset: `validation/github_event_external_v1.json`: **18 actual Git commits from five repositories** (Lightning-AI/litgpt, unslothai/unsloth, langchain-ai/langchain, run-llama/llama_index, sandeepmistry/arduino-LoRa).

Selection includes 11 positively annotated code changes and seven negatives (documentation-only Git changes / LoRa radio), with commit SHA, URL, message and changed-file list recorded before BGE-M3 evaluation.

No threshold refitting: use the **B-039 fixed experimental 0.425**. Live model run: [37828328027](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37828328027), artifact `github-external-holdout`.

| Metric | Local text gate only | Local text + BGE-M3 (0.425) |
| --- | ---: | ---: |
| TP | 4 | 4 |
| FN | 7 | 7 |
| TN | 7 | 7 |
| FP | 0 | 0 |
| Recall | 36.4% | 36.4% |

At least seven genuine LoRA/RAG-related implementation commits in this collection were missed, including `Add LoRA (#44)`, `Fix rope in LoRA-CausalSelfAttention`, and `KG RAG query engine`. They often need source-file context or are a supporting implementation that doesn't repeat the technology name in one local sentence.

**Crucial evaluation limitation:** This external holdout measured the **event message-only** local gate; it did **not** run every candidate through same-SHA patch enrichment. The result therefore rejects broad rollout of the *message-only* gate, but does **not** establish the recall of a fully patch-enriched live pipeline.

Another limitation: this is an author-curated holdout with labels made from commit message and changed-file review prior to scoring, not randomized sampling and not independently blind human annotation. Zero false positives on only seven negatives is weak evidence; none of these metrics justify production-quality guarantees.

## Next practical gate

**B-042:** Generalize immutable code-patch evidence handling beyond narrowly tailored LoRA examples, then test on a **separate fresh external Git sample**. The frozen B-041 holdout becomes a diagnostic set; do not refit threshold or claim performance on it as independently held out after examining failures. Keep cross-technology RAG/LoRA ambiguity protection, chronology and per-repository de-dup intact.

**B-037:** Before TOP-15 scoring, avoid double-counting a repository discovery snapshot plus historical commit from the same project as two independent adopters.
