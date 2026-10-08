"""High-precision event-local GitHub technology context gate (B-039).

Only specific, evaluated software/AI families are supported in v0.1.
Unknown domains require manual review; this is not a universal technology NER.
The matched event sentence is the unit of evidence: no whole-release keyword
bag, no repository created_at, no mutable current description as proof.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

_LORA_TOKEN = re.compile(r"(?i)(?<!\w)lora(?!\w)|(?i:lora(?:config|_target))|low[ -]rank adaptation")
_RAG_TOKEN = re.compile(r"(?i)(?<!\w)rag(?!\w)|retrieval[ -]augmented|ragretriever")
_RADIO = re.compile(r"(?i)lorawan|wireless|radio|gateway|sx127|rf frequencies|sensor network")
_IMAGE_ONLY = re.compile(r"(?i)diffusers|stable.diffusion|image generation|texture training")
_REJECT_ACTION = re.compile(r"(?i)remove.*(?:mention|reference|docs)|\b(?:list|catalog|mention|link to)\b.*\b(?:tools|libraries|docs)\b|formatting only|typo fixes|no implementation")
_LORA_DOMAIN = re.compile(r"(?i)\b(?:llms?|language models?|transformers?|fine[ -]?tun(?:e|ing)|adapters?|peft|qwen|llama|roberta|deberta|rank decomposition|lora(?:config|_target)|checkpoint|weights?)\b")
_RAG_DOMAIN = re.compile(r"(?i)\b(?:retriev\w*|documents?|embeddings?|vector|question answering|answer\w*|llms?|language models?|knowledge|ragretriever|indexing|chatgpt)\b")
_ACTION = re.compile(r"(?i)\b(?:add|implement|support|enable|integrat\w*|fix|train\w*|fine[ -]?tun\w*|stream\w*|build|merge|adapt\w*|checkpoint\w*|pipeline|config\w*|retriev\w*|index\w*|introduc\w*)\b|--lora_target|lora(?:config|_target)")
_LORA_NAME = re.compile(r"(?i)low[ -]rank adaptation|\blora\b|loraconfig|--lora_target")
_RAG_NAME = re.compile(r"(?i)retrieval[ -]augmented|\brag\b|ragretriever|chatgpt retrieval plugin")


@dataclass(frozen=True, slots=True)
class EventLocalGateDecision:
    status: str  # eligible, rejected, review_required
    reason: str
    evidence_span: str | None

    @property
    def eligible(self) -> bool:
        return self.status == "eligible"


def event_family(technology_direction: str) -> str | None:
    lowered = technology_direction.casefold().replace("-", " ")
    if ("low rank adaptation" in lowered or "lora" in lowered) and any(
        word in lowered for word in ("language model", "llm", "transformer")
    ):
        return "lora_llm"
    if "retrieval augmented" in lowered or "retrieval-augmented" in technology_direction.casefold():
        return "rag"
    return None


def evaluate_event_local(
    *, technology_direction: str, title: str, text: str
) -> EventLocalGateDecision:
    family = event_family(technology_direction)
    if family is None:
        return EventLocalGateDecision(
            "review_required", "no_calibrated_family_policy", None
        )
    # Split release notes into individual event assertions. Never inherit
    # an unrelated release headline (e.g. FlashAttention) as LoRA evidence.
    # For multi-sentence paragraphs, prefer the segment with identity term.
    lines = [segment.strip(" -*\t\r\n")
             for line in (text or title).splitlines()
             for segment in re.split(r"(?<=[.!?])\s+(?=[A-Z])", line)
             if segment.strip()]
    if title.strip() and title.strip() not in lines:
        lines.insert(0, title.strip())
    identity = _LORA_TOKEN if family == "lora_llm" else _RAG_TOKEN
    domain = _LORA_DOMAIN if family == "lora_llm" else _RAG_DOMAIN
    for span in lines:
        if not identity.search(span):
            continue
        if _REJECT_ACTION.search(span):
            continue
        if family == "lora_llm":
            if _RADIO.search(span) and not re.search(r"(?i)\b(?:llm|language model|transformer)\b", span):
                continue
            if _IMAGE_ONLY.search(span) and not re.search(r"(?i)\b(?:llm|language model|transformer|qwen|llama)\b", span):
                continue
            # A bare ambiguous 'lora' is not enough; require event-local
            # implementation context, never current repository metadata.
            if re.search(r"\bLoRa\b", span):
                continue
        else:
            if re.search(r"(?i)red[ ,/-]*amber[ ,/-]*green|traffic light|status dashboard", span):
                continue
        if not _ACTION.search(span):
            continue
        if not domain.search(span):
            continue
        if family == "rag" and not _RAG_NAME.search(span):
            continue
        if family == "lora_llm" and not _LORA_NAME.search(span):
            continue
        return EventLocalGateDecision("eligible", "local_technology_and_implementation_context", span[:1000])
    # Strict fallback for a SHORT commit subject that was not independently
    # descriptive: only same-SHA added source lines from GitHub commit diff
    # may establish the missing technical context. No mutable repo metadata.
    marker = "\\nGIT_PATCH_ADDED_LINES\\n"
    if family == "lora_llm" and marker in text:
        subject, patch = text.split(marker, 1)
        subject = subject.splitlines()[0].strip()
        if (
            re.search(r"(?i)\\b(?:add|implement|enable|introduce|support)\\b.*\\blora\\b", subject)
            and not _RADIO.search(subject)
            and not re.search(r"\\bLoRa\\b", subject)
            and re.search(r"(?m)^FILE [^\\n]+\\.(?:py|ts|tsx|js|rs|cpp|go)$", patch)
            and re.search(r"(?i)\\b(?:LoRAConfig|LoRAModel|loralib|mark_only_lora_as_trainable)\\b", patch)
        ):
            # This is a composite of two independently dated pieces of the
            # SAME commit: its authentic subject and its changed code lines.
            relevant = [line for line in patch.splitlines() if re.search(
                r"(?i)LoRAConfig|LoRAModel|loralib|mark_only_lora_as_trainable", line
            )]
            return EventLocalGateDecision(
                "eligible", "same_commit_source_diff_confirms_lora_implementation",
                (subject + "\\n" + "\\n".join(relevant[:3]))[:1000],
            )
    return EventLocalGateDecision("rejected", "no_event_local_implementation_evidence", None)
