# Timestamp-verified implementation transition benchmark

Status: **validated for the `software_ai` profile**  
Validation runner: `scripts/run_implementation_transition_validation.py` v0.1.1  
Case definition: `validation/retrospective_cases.yaml` v0.5.1  
Live CI run: `implementation-transition-validation` run `33275069636` — success

## Why this benchmark exists

The first retrospective attempt exposed a future-leakage failure: GitHub repository `created_at` is immutable, but the repository name/description matched by search can be edited years later. Therefore a repository created in 2020 can match a technology term introduced much later.

For historical implementation evidence, this project now treats the following as eligible source timestamps:

- first **relevant commit** timestamp;
- first **relevant release** timestamp;
- first **relevant tag** timestamp whose referenced commit is timestamped.

The following are explicitly **ineligible** as technology first-seen timestamps:

- repository `created_at` by itself;
- current repository name/description by itself.

Current repository metadata may still be used for present-day candidate discovery. It cannot backdate the technology.

## Results

| Case | Research origin | First verified implementation | Transition lag | Lead to preregistered ecosystem milestone | Result |
|---|---|---|---:|---:|---|
| Retrieval-Augmented Generation (RAG) | 2020-05-22 | 2020-09-22 16:29:58Z | 123 days | 912 days | validated |
| Low-Rank Adaptation (LoRA) | 2021-06-17 | 2021-09-16 21:48:51Z | 91 days | 435 days | validated |

### RAG evidence

Earliest verified implementation event in the configured candidates:

- repository: `huggingface/transformers`;
- event: commit `c754c41c6193565fecaf411b1de385bf90ab5c70`;
- title: `RAG (#6813)`;
- timestamp: `2020-09-22T16:29:58Z`;
- matched evidence includes `RagRetriever`, `rag`, `nlp`, `retrieval`.

The later ecosystem proxy was also independently verified:

- repository: `openai/chatgpt-retrieval-plugin`;
- event: commit `32bf09d16c4341571b530dd319d6678cb00f2d44`;
- title: `ChatGPT Retrieval Plugin`;
- timestamp: `2023-03-23T06:26:57Z`.

### LoRA evidence

Earliest verified implementation event in the configured candidates:

- repository: `microsoft/LoRA`;
- event: release `49709943` / tag `RoBERTa-base`;
- title: `RoBERTa base LoRA checkpoints`;
- timestamp: `2021-09-16T21:48:51Z`;
- matched evidence: `LoRA`.

The PEFT ecosystem evidence is timestamped from the first relevant commit rather than repository creation:

- repository: `huggingface/peft`;
- event: commit `e8160370247b3b61f57e59eb3f49acf9e3618b4b`;
- title: `add lora support`;
- timestamp: `2022-11-30T09:21:26Z`;
- matched evidence: `lora` + repository-specific context `support`.

The LoRA gate retains case-sensitive distinctive matching for `LoRA` so unrelated `LoRa` radio material does not become implementation evidence. Lowercase `lora` is accepted only when bounded contextual evidence makes the interpretation unambiguous.

## Methodological consequence

For `software_ai`, the evidence lifecycle is **profile-aware**:

```text
Research → Implementation → Product / Adoption
```

A patent is not mandatory for software. Patent/IP evidence can strengthen a software trend when present, but requiring it would create systematic false negatives.

For `hardware_semiconductor`, `materials_energy`, and `bio_medtech`, the patent/IP transition remains materially important and must be validated separately on representative cases.

## Production rule

The production GitHub path should be two-stage:

```text
present-day repository discovery
  → candidate repository
  → timestamp verification on commit / release / tag
  → normalized implementation Observation
  → semantic cluster gate
  → TrendState
```

Discovery answers **which repository may contain relevant evidence**. Timestamp verification answers **when the relevant technology evidence actually appeared**. These must not be conflated.
