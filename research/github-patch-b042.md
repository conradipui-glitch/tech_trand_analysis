# B-042 — same-SHA source diff evidence: test and measured limits

Status (2026-10-09): **implemented, unit/CI green, external holdout evaluated; production quality gate NOT PASSED**.

## Why the change was necessary

B-041's original fixed-threshold holdout (18 real commits) missed seven of eleven implementation cases (36.4% recall) when given only short Git commit text. Some changes, e.g. "Add LoRA" and "KG RAG query engine", have real code that cannot be inferred reliably from their subject alone. Trusting today's repository description or Git repo created_at would create historical future leakage.

## New explicit evidence contract

- The collector \`GitHubHistoryClient._enrich_commit_patch()\` retrieves \`/repos/<repo>/commits/<SHA>\` and reads **files[] from the exact same immutable commit**.
- \`extract_source_patch()\` returns a bounded sample of **added source lines** only; skips removed lines, comment lines, tests, notebooks, examples, docs and files without a recognized executable source extension. Raw GitHub commit title/text stays separate from \`VerifiedGitEvent.source_diff\`.
- \`evaluate_event_local(..., source_diff=...)\` is available only for the tested LoRA-LLM and RAG families. The structural patch field is verified separately and cannot be faked by typing \`GIT_PATCH_ADDED_LINES\` into the ordinary commit message. It still requires actual event-level technology-specific source symbols and context.
- GitHub radio LoRa modules, documentation-only patches, misleading filename-only evidence and unverified code comments do not qualify as LLM LoRA implementation.
- \`GitHubHistoryBridge\` passes this separate same-SHA field to the **opt-in experimental** event-local gate. Default production-like conservative history setting remains unchanged.

Files: \`src/tech_trend_analysis/github_patch_evidence.py\`, \`src/tech_trend_analysis/sources/github_history.py\`, \`src/tech_trend_analysis/github_event_local_gate.py\`, \`src/tech_trend_analysis/github_history_bridge.py\` and \`tests/test_github_patch_evidence.py\`.

## New evaluation frozen before scoring

- \`validation/github_patch_external_v2.json\`: 15 real Git commits, 6 manually labeled code changes, 9 negative cases, from **eight repositories unused in B-041**: \`artidoro/qlora\`, \`tloen/alpaca-lora\`, \`axolotl-ai-cloud/axolotl\`, \`infiniflow/ragflow\`, \`deepset-ai/haystack\`, \`langchain-ai/langgraph\`, \`jgromes/RadioLib\` and \`Lora-net/LoRaMac-node\`.
- Labels and literal SHA URLs were committed **before** \`scripts/evaluate_github_patch_external.py\` fetched exact-sha patch content / ran BGE-M3. No labels or threshold were changed after viewing the errors.
- Same \`BAAI/bge-m3\` model and **fixed B-039 threshold = 0.425**. No fitting on these samples.
- Full run: [GitHub Actions #37832290691](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37832290691) with \`github-patch-external-v2\` artifact including similarity, source-diff excerpts and all predictions.

| Variant | TP | FN | TN | FP | Recall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Event message only | 1 | 5 | 9 | 0 | 16.7% |
| Same-SHA executable patch + event message | **3** | **3** | **9** | **0** | **50.0%** |

On this small manually chosen test set, recall **tripled**, but 3 of 6 actual implementation changes were still missed. The three false negatives:
1. \`qlora-tokenizer\`: actual QLoRA tokenizer code fix but lacks a strong LoRA code identifier in selected added lines; similarity 0.38856, no event-local proof.
2. \`qlora-update\`: generic commit message \`Update qlora.py\` and no selected relevant added source line; similarity 0.36270.
3. \`ragflow-qa\`: relevant RAGFlow retrieval/QA implementation work but no sufficiently explicit local technology assertion; similarity 0.59035 (above threshold, yet rejected by high-precision contextual rule).

**Not a blind evaluation**: researchers intentionally sampled commits and labeled them using title/file context. This supports debugging and relative comparison, not reliable population-level recall or false positive rate estimates. Zero FP on nine negatives does not prove universal precision. Results from different B-041/B-042 samples must not be presented as one apples-to-apples improvement; the baseline/patch comparison *within B-042* is the valid comparison.

## Safety and next step

- No experimental event-local evidence has been rolled into public Cloudflare TOP-15 ranking or general Emerging Score.
- Do not simply drop 0.425 for QLoRA. For short supporting fixes, first prove a verifiable dependency/relationship to a **previously confirmed same-repository technology module**, then attach a subordinate event rather than creating independent adoption or backdating a trend from an isolated lexical hit.
- B-043 next: test bounded verified module ancestry / source-file history for supporting patches (and file renamed/moved cases) on a new, pre-frozen real Git sample. Avoid counting multiple commits from the same repository as independent evidence.
- B-037 still needed before production ranking: don't count today's GitHub repository snapshot plus historical implementation commit as two independent adopters.

CI: unit/regression tests on the new code and injection guard passed (e.g. [run #37832386648](https://github.com/conradipui-glitch/tech_trand_analysis/actions/runs/37832386648)).
