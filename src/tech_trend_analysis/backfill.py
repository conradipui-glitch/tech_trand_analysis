from __future__ import annotations

import calendar
import hashlib
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from .sources.openalex import OpenAlexQuery
from .trend_state import TrendState


@dataclass(frozen=True, slots=True)
class BackfillPolicy:
    initial_months: int
    expansion_months: int
    max_months: int
    boundary_margin_months: int = 2

    def __post_init__(self) -> None:
        if self.initial_months < 1:
            raise ValueError("initial_months must be >= 1")
        if self.expansion_months < 1:
            raise ValueError("expansion_months must be >= 1")
        if self.max_months < self.initial_months:
            raise ValueError("max_months must be >= initial_months")
        if self.boundary_margin_months < 0:
            raise ValueError("boundary_margin_months must be >= 0")


PROFILE_BACKFILL_POLICIES: dict[str, BackfillPolicy] = {
    "software_ai": BackfillPolicy(24, 12, 60, 2),
    "hardware_semiconductor": BackfillPolicy(36, 18, 96, 3),
    "materials_energy": BackfillPolicy(48, 24, 120, 4),
    "bio_medtech": BackfillPolicy(48, 24, 120, 4),
    "mixed": BackfillPolicy(36, 18, 84, 3),
}


@dataclass(frozen=True, slots=True)
class TrendQueryDescriptor:
    trend_id: str
    query_text: str
    representative_title: str
    source_topics: tuple[str, ...]
    classifications: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BackfillPlan:
    trend_id: str
    provider: str
    technology_direction: str
    source_profile: str
    query_text: str
    from_date: date
    to_date: date
    iteration: int
    reason: str
    max_history_start: date

    @property
    def query_id(self) -> str:
        payload = "|".join(
            [
                self.trend_id,
                self.provider,
                self.from_date.isoformat(),
                self.to_date.isoformat(),
                str(self.iteration),
            ]
        )
        digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
        return f"backfill:{digest}"


@dataclass(frozen=True, slots=True)
class HistoricalGateResult:
    accepted_ids: tuple[str, ...]
    rejected_ids: tuple[str, ...]
    similarities: dict[str, float]


class AdaptiveBackfillPlanner:
    def __init__(
        self,
        *,
        policies: Mapping[str, BackfillPolicy] | None = None,
    ) -> None:
        self.policies = dict(policies or PROFILE_BACKFILL_POLICIES)

    def build_descriptor(
        self,
        state: TrendState,
        observations_by_id: Mapping[str, dict[str, Any]],
    ) -> TrendQueryDescriptor:
        observations = [
            observations_by_id[observation_id]
            for observation_id in sorted(state.observation_ids)
            if observation_id in observations_by_id
        ]
        if not observations:
            raise ValueError(f"no observations available for trend {state.trend_id}")

        titles = [_required_string(observation, "title") for observation in observations]
        representative_title = _lexical_medoid_title(observations, titles)

        topic_counts: Counter[str] = Counter()
        classification_counts: Counter[str] = Counter()
        for observation in observations:
            topics = observation.get("source_topics")
            if isinstance(topics, list):
                topic_counts.update(
                    topic.strip()
                    for topic in topics
                    if isinstance(topic, str) and topic.strip()
                )
            classifications = observation.get("classifications")
            if isinstance(classifications, list):
                for item in classifications:
                    if not isinstance(item, dict):
                        continue
                    label = item.get("label") or item.get("value")
                    if isinstance(label, str) and label.strip():
                        classification_counts[label.strip()] += 1

        source_topics = tuple(value for value, _ in topic_counts.most_common(5))
        classifications = tuple(value for value, _ in classification_counts.most_common(5))

        # Use a real representative evidence title instead of an LLM-invented label.
        # Source topics add bounded context when available, but the query stays short.
        query_parts = [representative_title]
        for topic in source_topics[:2]:
            if topic.casefold() not in representative_title.casefold():
                query_parts.append(topic)
        query_text = " ".join(query_parts).strip()[:320]

        return TrendQueryDescriptor(
            trend_id=state.trend_id,
            query_text=query_text,
            representative_title=representative_title,
            source_topics=source_topics,
            classifications=classifications,
        )

    def initial_plan(
        self,
        state: TrendState,
        descriptor: TrendQueryDescriptor,
        *,
        as_of: date,
        provider: str = "openalex",
    ) -> BackfillPlan:
        policy = self._policy(state.profile)
        month_start = as_of.replace(day=1)
        from_date = _shift_months(month_start, -(policy.initial_months - 1))
        max_history_start = _shift_months(month_start, -(policy.max_months - 1))
        return BackfillPlan(
            trend_id=state.trend_id,
            provider=provider,
            technology_direction=state.technology_direction,
            source_profile=state.profile,
            query_text=descriptor.query_text,
            from_date=from_date,
            to_date=as_of,
            iteration=0,
            reason="initial_bounded_window",
            max_history_start=max_history_start,
        )

    def should_expand(self, state: TrendState, plan: BackfillPlan) -> bool:
        if plan.from_date <= plan.max_history_start:
            return False
        policy = self._policy(state.profile)
        first_seen = _parse_date(state.first_seen)
        boundary_end = _shift_months(plan.from_date, policy.boundary_margin_months)
        return first_seen < boundary_end

    def expand(self, state: TrendState, plan: BackfillPlan) -> BackfillPlan | None:
        if not self.should_expand(state, plan):
            return None
        policy = self._policy(state.profile)
        next_to = plan.from_date - timedelta(days=1)
        requested_start = _shift_months(plan.from_date, -policy.expansion_months)
        next_from = max(plan.max_history_start, requested_start)
        if next_from > next_to:
            return None
        return BackfillPlan(
            trend_id=plan.trend_id,
            provider=plan.provider,
            technology_direction=plan.technology_direction,
            source_profile=plan.source_profile,
            query_text=plan.query_text,
            from_date=next_from,
            to_date=next_to,
            iteration=plan.iteration + 1,
            reason="left_boundary_signal",
            max_history_start=plan.max_history_start,
        )

    def to_openalex_query(
        self,
        plan: BackfillPlan,
        *,
        per_page: int = 100,
        max_pages: int = 20,
    ) -> OpenAlexQuery:
        if plan.provider != "openalex":
            raise ValueError("plan provider must be openalex")
        return OpenAlexQuery(
            technology_direction=plan.technology_direction,
            source_profile=plan.source_profile,
            query_text=plan.query_text,
            query_id=plan.query_id,
            from_date=plan.from_date,
            to_date=plan.to_date,
            per_page=per_page,
            max_pages=max_pages,
        )

    def _policy(self, profile: str) -> BackfillPolicy:
        policy = self.policies.get(profile)
        if policy is None:
            raise ValueError(f"no backfill policy for profile: {profile}")
        return policy


def gate_historical_vectors(
    state: TrendState,
    *,
    observation_ids: Sequence[str],
    vectors: Sequence[Sequence[float]],
    similarity_threshold: float = 0.82,
) -> HistoricalGateResult:
    """Keep historical evidence semantically close to the existing trend centroid.

    Targeted provider search is retrieval, not proof of cluster membership. This
    gate prevents a broad historical query from pulling an adjacent technology
    into the TrendState and artificially moving first_seen backwards.
    """
    if not 0 < similarity_threshold <= 1:
        raise ValueError("similarity_threshold must be in (0, 1]")
    ids = [str(value).strip() for value in observation_ids]
    matrix = np.asarray(vectors, dtype=np.float32)
    if matrix.ndim != 2 or len(ids) != matrix.shape[0]:
        raise ValueError("observation_ids and vectors must have matching rows")
    if not ids:
        return HistoricalGateResult((), (), {})
    if not np.isfinite(matrix).all():
        raise ValueError("vectors must be finite")

    centroid = _normalized(np.asarray(state.centroid, dtype=np.float32))
    if matrix.shape[1] != centroid.shape[0]:
        raise ValueError("historical vectors must match TrendState centroid dimension")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    if np.any(norms == 0):
        raise ValueError("historical vectors must be non-zero")
    normalized = matrix / norms
    scores = normalized @ centroid

    accepted: list[str] = []
    rejected: list[str] = []
    similarities: dict[str, float] = {}
    for observation_id, raw_score in zip(ids, scores, strict=True):
        score = float(np.clip(raw_score, -1.0, 1.0))
        similarities[observation_id] = score
        if score >= similarity_threshold:
            accepted.append(observation_id)
        else:
            rejected.append(observation_id)

    return HistoricalGateResult(
        accepted_ids=tuple(accepted),
        rejected_ids=tuple(rejected),
        similarities=similarities,
    )


def _lexical_medoid_title(
    observations: list[dict[str, Any]],
    titles: list[str],
) -> str:
    if len(titles) == 1:
        return titles[0]
    documents: list[str] = []
    for observation, title in zip(observations, titles, strict=True):
        text = observation.get("text")
        documents.append(f"{title} {text if isinstance(text, str) else ''}".strip())
    try:
        matrix = TfidfVectorizer(
            lowercase=True,
            ngram_range=(1, 2),
            token_pattern=r"(?u)\b\w[\w-]+\b",
        ).fit_transform(documents)
    except ValueError:
        return titles[0]
    similarities = cosine_similarity(matrix)
    mean_similarity = similarities.mean(axis=1)
    return titles[int(np.argmax(mean_similarity))]


def _shift_months(value: date, months: int) -> date:
    total = value.year * 12 + (value.month - 1) + months
    year, month_index = divmod(total, 12)
    month = month_index + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def _parse_date(value: str) -> date:
    raw = value.strip().replace("Z", "+00:00")
    if "T" not in raw:
        return date.fromisoformat(raw)
    return datetime.fromisoformat(raw).date()


def _normalized(vector: np.ndarray) -> np.ndarray:
    if vector.ndim != 1 or vector.size == 0 or not np.isfinite(vector).all():
        raise ValueError("centroid must be a finite non-empty 1D vector")
    norm = float(np.linalg.norm(vector))
    if norm == 0:
        raise ValueError("centroid must be non-zero")
    return vector / norm


def _required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
