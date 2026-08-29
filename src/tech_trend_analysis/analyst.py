from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

import httpx


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_ANALYST_MODEL = "deepseek-v4-flash"
INSUFFICIENT_PROBLEM_EVIDENCE = "Недостаточно подтверждённых данных для вывода о проблеме и преимуществе."
ANALYST_FIELDS = (
    "human_summary",
    "why_now",
    "problem_advantage",
    "caveat",
    "what_to_watch_next",
    "analyst_note",
    "used_source_refs",
)


class AnalystError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AnalystNarrative:
    human_summary: str
    why_now: str
    problem_advantage: str
    caveat: str
    what_to_watch_next: str
    analyst_note: str
    used_source_refs: tuple[str, ...]
    model: str = DEEPSEEK_ANALYST_MODEL

    def to_dict(self) -> dict[str, Any]:
        return {
            "human_summary": self.human_summary,
            "why_now": self.why_now,
            "problem_advantage": self.problem_advantage,
            "caveat": self.caveat,
            "what_to_watch_next": self.what_to_watch_next,
            "analyst_note": self.analyst_note,
            "used_source_refs": list(self.used_source_refs),
            "model": self.model,
        }


def source_refs(trend: Mapping[str, Any]) -> set[str]:
    refs: set[str] = set()
    for item in trend.get("evidence", []) or []:
        if isinstance(item, Mapping):
            for key in ("observation_id", "url", "source_ref", "raw_ref"):
                value = item.get(key)
                if value:
                    refs.add(str(value))
    for item in trend.get("sources", []) or []:
        if isinstance(item, Mapping):
            for key in ("id", "url", "source_ref"):
                value = item.get(key)
                if value:
                    refs.add(str(value))
        elif item:
            refs.add(str(item))
    return refs


def has_problem_advantage_evidence(trend: Mapping[str, Any]) -> bool:
    value = trend.get("problem_advantage_evidence")
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple)):
        return bool(value)
    return False


def build_messages(trend: Mapping[str, Any]) -> list[dict[str, str]]:
    problem_supported = has_problem_advantage_evidence(trend)
    problem_instruction = (
        "The input contains explicit problem_advantage_evidence. You may summarize only that supplied evidence in problem_advantage. "
        if problem_supported
        else f"The input contains NO validated problem/advantage evidence. problem_advantage MUST be exactly: {INSUFFICIENT_PROBLEM_EVIDENCE} "
    )
    system = (
        "You are the final analyst-editor for an emerging-technology detector. "
        "The detector, not you, has already selected and scored this trend. "
        "Use ONLY facts present in the supplied JSON. Your general knowledge is forbidden as evidence. "
        "Never invent companies, dates, sources, technology capabilities, problems solved, advantages, market adoption, causal claims or sector use cases. "
        "Do not change score, confidence, stage, ranking or first_seen. "
        "human_summary must summarize the supplied score/metrics/evidence only. "
        "why_now must refer only to supplied temporal/evidence changes; if they do not support a conclusion, say evidence is insufficient. "
        + problem_instruction +
        "caveat must be grounded in supplied limitations/diagnostics. "
        "what_to_watch_next and analyst_note are forward-looking investigation suggestions or hypotheses, never statements that an event has occurred; analyst_note is not financial advice. "
        "Write concise Russian for a professional bank analytics audience. "
        "Return one JSON object with exactly these keys: human_summary, why_now, problem_advantage, caveat, what_to_watch_next, analyst_note, used_source_refs. "
        "used_source_refs may contain only identifiers or URLs already present in the input."
    )
    user = json.dumps(dict(trend), ensure_ascii=False, separators=(",", ":"))
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def parse_narrative(
    content: str,
    *,
    allowed_source_refs: set[str],
    problem_advantage_supported: bool = True,
    model: str = DEEPSEEK_ANALYST_MODEL,
) -> AnalystNarrative:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        raise AnalystError("analyst returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AnalystError("analyst response must be a JSON object")
    missing = [key for key in ANALYST_FIELDS if key not in payload]
    if missing:
        raise AnalystError(f"analyst response missing fields: {missing}")

    refs = tuple(str(value) for value in (payload.get("used_source_refs") or []))
    unknown = sorted(set(refs) - allowed_source_refs)
    if unknown:
        raise AnalystError(f"analyst cited unknown source refs: {unknown}")

    text_values: dict[str, str] = {}
    for key in ANALYST_FIELDS[:-1]:
        value = str(payload.get(key, "")).strip()
        if not value:
            raise AnalystError(f"analyst field {key} is empty")
        text_values[key] = value

    # Fail closed on the assignment's most hallucination-prone field. Until a
    # separate evidence-enrichment stage has supplied explicit problem/advantage
    # evidence, the public narrative is deterministic rather than model-created.
    if not problem_advantage_supported:
        text_values["problem_advantage"] = INSUFFICIENT_PROBLEM_EVIDENCE

    return AnalystNarrative(
        **text_values,
        used_source_refs=refs,
        model=model,
    )


class DeepSeekAnalyst:
    """Grounded post-ranking narrative layer.

    This class must never participate in discovery, clustering or TOP-15 ranking.
    It receives an already-scored trend and only produces human-readable narrative.
    Unsupported problem/advantage claims are replaced with a deterministic
    insufficient-evidence message until evidence enrichment has run.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEEPSEEK_ANALYST_MODEL,
        base_url: str = DEEPSEEK_BASE_URL,
        timeout_seconds: float = 60.0,
    ) -> None:
        if not api_key.strip():
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def enrich(self, trend: Mapping[str, Any]) -> AnalystNarrative:
        allowed_refs = source_refs(trend)
        problem_supported = has_problem_advantage_evidence(trend)
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "thinking": {"type": "disabled"},
                "response_format": {"type": "json_object"},
                "messages": build_messages(trend),
                "max_tokens": 1400,
            },
            timeout=self.timeout_seconds,
        )
        if response.status_code >= 400:
            raise AnalystError(f"DeepSeek API error {response.status_code}: {response.text[:500]}")
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise AnalystError("unexpected DeepSeek response shape") from exc
        return parse_narrative(
            str(content),
            allowed_source_refs=allowed_refs,
            problem_advantage_supported=problem_supported,
            model=self.model,
        )
