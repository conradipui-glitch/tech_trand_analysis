from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping

import numpy as np

from .trend_state import PeriodBucket, TrendState


SCORE_VERSION = "0.1.0"

COMPONENT_WEIGHTS: dict[str, float] = {
    "growth": 0.22,
    "acceleration": 0.18,
    "novelty": 0.18,
    "evidence_diversity": 0.14,
    "actor_diversity": 0.10,
    "recency": 0.08,
    "persistence": 0.10,
}

# Maturity is a subtractive term rather than a positive weighted component.
MAX_MATURITY_PENALTY_POINTS = 30.0
DYNAMIC_PRIOR = 25.0


@dataclass(frozen=True, slots=True)
class ScoreComponent:
    value: float
    explanation: str
    reliability: float = 1.0

    def __post_init__(self) -> None:
        if not 0 <= self.value <= 100:
            raise ValueError("component value must be in [0, 100]")
        if not 0 <= self.reliability <= 1:
            raise ValueError("component reliability must be in [0, 1]")

    def to_contract(self) -> dict[str, Any]:
        return {
            "value": round(self.value, 4),
            "explanation": self.explanation,
        }


@dataclass(frozen=True, slots=True)
class EmergingScoreResult:
    trend_id: str
    version: str
    total: float
    confidence: float
    stage: str
    components: dict[str, ScoreComponent]

    def to_contract(self) -> dict[str, Any]:
        return {
            "total": round(self.total, 4),
            "confidence": round(self.confidence, 4),
            "components": {
                key: component.to_contract()
                for key, component in self.components.items()
            },
        }


class EmergingScorer:
    """Transparent provisional emerging-trend score over TrendState history.

    B-019 intentionally separates ranking score from evidence confidence. Weights
    and thresholds are v0 hypotheses and must be calibrated by retrospective B-030
    tests before being treated as production methodology.
    """

    def __init__(
        self,
        *,
        component_weights: Mapping[str, float] | None = None,
        max_maturity_penalty_points: float = MAX_MATURITY_PENALTY_POINTS,
    ) -> None:
        self.weights = dict(component_weights or COMPONENT_WEIGHTS)
        if set(self.weights) != set(COMPONENT_WEIGHTS):
            raise ValueError(f"component_weights must define {sorted(COMPONENT_WEIGHTS)}")
        if not math.isclose(sum(self.weights.values()), 1.0, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError("component weights must sum to 1")
        if not 0 <= max_maturity_penalty_points <= 100:
            raise ValueError("max_maturity_penalty_points must be in [0, 100]")
        self.max_maturity_penalty_points = max_maturity_penalty_points

    def score(self, state: TrendState, *, as_of: date) -> EmergingScoreResult:
        first_seen = _parse_date(state.first_seen)
        last_seen = _parse_date(state.last_seen)
        if first_seen > as_of:
            raise ValueError("TrendState first_seen cannot be after as_of")

        age_months = _month_distance(first_seen, as_of)
        inactivity_months = max(0, _month_distance(last_seen, as_of))
        counts = _recent_month_counts(state.periods, as_of=as_of, months=12)

        growth = _growth_component(counts)
        acceleration = _acceleration_component(counts)
        novelty = _novelty_component(age_months)
        evidence = _evidence_component(state)
        actors = _actor_component(state.actor_diversity)
        recency = _recency_component(inactivity_months)
        persistence = _persistence_component(counts, age_months=age_months)
        maturity = _maturity_component(state, age_months=age_months)

        positive_components = {
            "growth": growth,
            "acceleration": acceleration,
            "novelty": novelty,
            "evidence_diversity": evidence,
            "actor_diversity": actors,
            "recency": recency,
            "persistence": persistence,
        }
        raw = sum(
            self.weights[name] * component.value
            for name, component in positive_components.items()
        )
        total = _clamp(
            raw - self.max_maturity_penalty_points * (maturity.value / 100.0),
            0.0,
            100.0,
        )
        confidence = _confidence(state, positive_components)
        stage = _stage(state, total=total, confidence=confidence, maturity=maturity.value)

        components = dict(positive_components)
        components["maturity_penalty"] = maturity
        return EmergingScoreResult(
            trend_id=state.trend_id,
            version=SCORE_VERSION,
            total=total,
            confidence=confidence,
            stage=stage,
            components=components,
        )


def _growth_component(counts: list[int]) -> ScoreComponent:
    recent = float(np.mean(counts[-3:]))
    previous = float(np.mean(counts[-6:-3]))
    ratio = (recent + 0.5) / (previous + 0.5)
    raw_value = _clamp(50.0 + 25.0 * math.log2(ratio), 0.0, 100.0)
    observed_months = sum(1 for value_ in counts[-6:] if value_ > 0)
    reliability = min(1.0, observed_months / 4.0)
    value = _shrink_to_prior(raw_value, reliability)
    return ScoreComponent(
        value=value,
        reliability=reliability,
        explanation=(
            f"Recent 3-month mean={recent:.2f}, previous 3-month mean={previous:.2f}; "
            f"raw growth={raw_value:.1f}, reliability={reliability:.2f}, sparse history shrinks toward {DYNAMIC_PRIOR:.0f}."
        ),
    )


def _acceleration_component(counts: list[int]) -> ScoreComponent:
    previous = np.asarray(counts[-6:-3], dtype=np.float64)
    recent = np.asarray(counts[-3:], dtype=np.float64)
    previous_velocity = _normalized_slope(previous)
    recent_velocity = _normalized_slope(recent)
    delta = recent_velocity - previous_velocity
    raw_value = _clamp(50.0 + 50.0 * math.tanh(delta * 2.0), 0.0, 100.0)
    active = sum(1 for value_ in counts[-6:] if value_ > 0)
    reliability = min(1.0, active / 5.0)
    value = _shrink_to_prior(raw_value, reliability)
    return ScoreComponent(
        value=value,
        reliability=reliability,
        explanation=(
            f"Normalized recent velocity={recent_velocity:.3f}, previous velocity={previous_velocity:.3f}; "
            f"delta={delta:.3f}, raw acceleration={raw_value:.1f}, reliability={reliability:.2f}."
        ),
    )


def _novelty_component(age_months: int) -> ScoreComponent:
    value = 100.0 * math.exp(-max(0, age_months - 2) / 30.0)
    return ScoreComponent(
        value=_clamp(value, 0.0, 100.0),
        explanation=f"First sustained evidence is approximately {age_months} months old; younger states score higher.",
    )


def _recency_component(inactivity_months: int) -> ScoreComponent:
    value = 100.0 * math.exp(-inactivity_months / 12.0)
    return ScoreComponent(
        value=_clamp(value, 0.0, 100.0),
        explanation=f"Latest evidence is approximately {inactivity_months} months old.",
    )


def _evidence_component(state: TrendState) -> ScoreComponent:
    present = {key for key, count in state.evidence_counts.items() if count > 0}
    buckets = _evidence_buckets(state.profile)
    value = 0.0
    satisfied: list[str] = []
    for bucket_name, types, weight in buckets:
        if present.intersection(types):
            value += weight * 100.0
            satisfied.append(bucket_name)

    transition_bonus = 0.0
    research_at = state.first_evidence_at.get("research")
    applied_dates = [
        state.first_evidence_at[key]
        for key in ("patent", "implementation", "product", "adoption")
        if key in state.first_evidence_at
    ]
    if research_at and applied_dates and min(applied_dates) >= research_at:
        transition_bonus = 10.0
        value += transition_bonus

    value = _clamp(value, 0.0, 100.0)
    reliability = min(1.0, state.observation_count / 6.0)
    return ScoreComponent(
        value=value,
        reliability=reliability,
        explanation=(
            f"Profile-aware evidence buckets present={satisfied or ['none']}; "
            f"research→applied transition bonus={transition_bonus:.0f}."
        ),
    )


def _actor_component(actor_count: int) -> ScoreComponent:
    value = 100.0 * math.log1p(max(0, actor_count)) / math.log1p(20)
    return ScoreComponent(
        value=_clamp(value, 0.0, 100.0),
        reliability=min(1.0, actor_count / 5.0),
        explanation=f"Distinct normalized actors={actor_count}; logarithmic saturation at roughly 20 actors.",
    )


def _persistence_component(counts: list[int], *, age_months: int) -> ScoreComponent:
    available = min(6, max(1, age_months + 1))
    window = counts[-available:]
    active = sum(1 for value in window if value > 0)
    longest = _longest_positive_run(window)
    active_ratio = active / available
    run_ratio = min(1.0, longest / min(3, available))
    raw_value = 70.0 * active_ratio + 30.0 * run_ratio
    reliability = min(1.0, available / 4.0)
    value = _shrink_to_prior(raw_value, reliability)
    return ScoreComponent(
        value=_clamp(value, 0.0, 100.0),
        reliability=reliability,
        explanation=(
            f"Active months={active}/{available} in recent available window; "
            f"longest consecutive active run={longest}; raw persistence={raw_value:.1f}, reliability={reliability:.2f}."
        ),
    )


def _maturity_component(state: TrendState, *, age_months: int) -> ScoreComponent:
    age_factor = _clamp((age_months - 36) / 60.0, 0.0, 1.0)
    volume_factor = _clamp(
        math.log1p(state.observation_count) / math.log1p(500),
        0.0,
        1.0,
    )
    market_factor = 1.0 if {"product", "adoption"}.intersection(state.evidence_counts) else 0.0
    value = 100.0 * age_factor * (0.70 + 0.20 * volume_factor + 0.10 * market_factor)
    return ScoreComponent(
        value=_clamp(value, 0.0, 100.0),
        explanation=(
            f"Age={age_months} months, observations={state.observation_count}, "
            f"market/adoption evidence={'yes' if market_factor else 'no'}; penalty activates after 36 months."
        ),
    )


def _confidence(
    state: TrendState,
    positive_components: Mapping[str, ScoreComponent],
) -> float:
    volume = min(1.0, math.log1p(state.observation_count) / math.log1p(30))
    provider = min(1.0, state.provider_diversity / 3.0)
    evidence = min(1.0, state.evidence_diversity / 3.0)
    temporal = min(1.0, len(state.periods) / 6.0)
    dynamic_reliability = (
        positive_components["growth"].reliability
        + positive_components["acceleration"].reliability
        + positive_components["persistence"].reliability
    ) / 3.0
    confidence = (
        0.30 * volume
        + 0.20 * provider
        + 0.20 * evidence
        + 0.15 * temporal
        + 0.15 * dynamic_reliability
    )
    return _clamp(confidence, 0.0, 1.0)


def _stage(
    state: TrendState,
    *,
    total: float,
    confidence: float,
    maturity: float,
) -> str:
    if total < 40.0:
        return "unknown"
    has_market = bool({"product", "adoption"}.intersection(state.evidence_counts))
    if has_market and total >= 50.0 and maturity < 60.0:
        return "early_adoption"
    if total >= 60.0 and confidence >= 0.45:
        return "emerging"
    return "weak_signal"


def _evidence_buckets(profile: str) -> list[tuple[str, set[str], float]]:
    if profile == "software_ai":
        return [
            ("research", {"research"}, 0.25),
            ("applied", {"implementation", "patent"}, 0.35),
            ("market", {"product", "adoption", "investment"}, 0.25),
            ("context", {"regulation", "analysis"}, 0.15),
        ]
    if profile in {"hardware_semiconductor", "materials_energy", "bio_medtech"}:
        return [
            ("research", {"research"}, 0.25),
            ("ip", {"patent"}, 0.30),
            ("implementation", {"implementation", "product"}, 0.25),
            ("market", {"adoption", "investment"}, 0.15),
            ("context", {"regulation", "analysis"}, 0.05),
        ]
    return [
        ("research", {"research"}, 0.25),
        ("applied", {"patent", "implementation"}, 0.30),
        ("market", {"product", "adoption", "investment"}, 0.25),
        ("context", {"regulation", "analysis"}, 0.20),
    ]


def _recent_month_counts(
    periods: Mapping[str, PeriodBucket],
    *,
    as_of: date,
    months: int,
) -> list[int]:
    if months < 1:
        raise ValueError("months must be >= 1")
    current = as_of.replace(day=1)
    keys = [_month_key(_shift_month(current, offset)) for offset in range(-(months - 1), 1)]
    return [periods[key].total if key in periods else 0 for key in keys]


def _normalized_slope(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    x = np.arange(values.size, dtype=np.float64)
    slope = float(np.polyfit(x, values, 1)[0])
    return slope / (float(np.mean(values)) + 1.0)


def _longest_positive_run(values: list[int]) -> int:
    longest = 0
    current = 0
    for value in values:
        if value > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def _month_distance(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month)


def _shift_month(value: date, offset: int) -> date:
    total = value.year * 12 + value.month - 1 + offset
    year, month_index = divmod(total, 12)
    return date(year, month_index + 1, 1)


def _month_key(value: date) -> str:
    return f"{value.year:04d}-{value.month:02d}"


def _parse_date(value: str) -> date:
    raw = value.strip().replace("Z", "+00:00")
    if "T" not in raw:
        return date.fromisoformat(raw)
    return datetime.fromisoformat(raw).date()


def _shrink_to_prior(value: float, reliability: float) -> float:
    return _clamp(
        reliability * value + (1.0 - reliability) * DYNAMIC_PRIOR,
        0.0,
        100.0,
    )


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
