from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


SUPPORTED_PROFILES = {
    "software_ai",
    "hardware_semiconductor",
    "materials_energy",
    "bio_medtech",
    "mixed",
}


_PROFILE_SIGNALS: dict[str, tuple[str, ...]] = {
    "software_ai": (
        "artificial intelligence",
        "ai",
        "machine learning",
        "deep learning",
        "large language model",
        "llm",
        "ai agent",
        "agentic",
        "software",
        "framework",
        "developer tool",
        "искусственный интеллект",
        "ии",
        "машинное обучение",
        "нейросет",
        "языковая модель",
        "ии агент",
        "агентн",
        "программ",
    ),
    "hardware_semiconductor": (
        "semiconductor",
        "chip",
        "processor",
        "accelerator",
        "neuromorphic",
        "photonic",
        "microelectronics",
        "compute hardware",
        "quantum processor",
        "полупровод",
        "чип",
        "процессор",
        "ускорител",
        "нейроморф",
        "фотоник",
        "микроэлектрон",
        "квантовый процессор",
    ),
    "materials_energy": (
        "material",
        "battery",
        "batteries",
        "solid-state battery",
        "solid-state batteries",
        "electrolyte",
        "lithium",
        "sodium ion",
        "hydrogen",
        "energy storage",
        "solar cell",
        "catalyst",
        "материал",
        "батар",
        "батареи",
        "аккумулятор",
        "твердотел",
        "электролит",
        "литий",
        "натрий",
        "водород",
        "накоплен",
        "солнечн",
        "катализ",
    ),
    "bio_medtech": (
        "biotech",
        "biotechnology",
        "medical",
        "medtech",
        "diagnostic",
        "therapy",
        "therapeutic",
        "genomic",
        "gene editing",
        "drug discovery",
        "protein",
        "био",
        "медицин",
        "диагност",
        "терап",
        "геном",
        "генн",
        "лекарств",
        "белок",
        "фарма",
    ),
}


@dataclass(frozen=True, slots=True)
class ProviderRoute:
    provider: str
    enabled: bool
    role: str
    evidence_type: str
    collection_priority: float
    query_strategy: str | None = None


@dataclass(frozen=True, slots=True)
class RouteDecision:
    technology_direction: str
    profile: str
    confidence: float
    matched_signals: tuple[str, ...]
    providers: tuple[ProviderRoute, ...]

    @property
    def enabled_providers(self) -> tuple[ProviderRoute, ...]:
        return tuple(provider for provider in self.providers if provider.enabled)


class SourceRouter:
    """Classify a technology direction and resolve provider policies from config."""

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = _validate_config(config)

    @classmethod
    def from_yaml(cls, path: str | Path) -> "SourceRouter":
        payload = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("source config root must be an object")
        return cls(payload)

    def route(
        self,
        technology_direction: str,
        *,
        profile_override: str | None = None,
    ) -> RouteDecision:
        direction = technology_direction.strip()
        if not direction:
            raise ValueError("technology_direction must not be empty")

        if profile_override is not None:
            if profile_override not in SUPPORTED_PROFILES:
                raise ValueError(f"unsupported source profile: {profile_override}")
            profile = profile_override
            confidence = 1.0
            matched_signals: tuple[str, ...] = ()
        else:
            profile, confidence, matched_signals = classify_direction(direction)

        providers = self._providers_for_profile(profile)
        return RouteDecision(
            technology_direction=direction,
            profile=profile,
            confidence=confidence,
            matched_signals=matched_signals,
            providers=providers,
        )

    def _providers_for_profile(self, profile: str) -> tuple[ProviderRoute, ...]:
        profile_cfg = self.config["profiles"].get(profile)
        if not isinstance(profile_cfg, dict):
            raise ValueError(f"profile missing from source config: {profile}")

        policies = profile_cfg.get("providers")
        if not isinstance(policies, dict):
            raise ValueError(f"profile {profile} is missing provider policies")

        provider_defs = self.config["providers"]
        routes: list[ProviderRoute] = []

        for provider_id, policy in policies.items():
            provider_def = provider_defs.get(provider_id)
            if not isinstance(provider_def, dict):
                raise ValueError(
                    f"profile {profile} references unknown provider: {provider_id}"
                )
            if not isinstance(policy, dict):
                raise ValueError(
                    f"profile {profile} provider policy must be object: {provider_id}"
                )

            priority = float(policy.get("collection_priority", 0.0))
            if not 0.0 <= priority <= 1.0:
                raise ValueError(
                    f"collection_priority must be 0..1 for {profile}/{provider_id}"
                )

            routes.append(
                ProviderRoute(
                    provider=provider_id,
                    enabled=bool(policy.get("enabled", True)),
                    role=str(
                        policy.get("role")
                        or provider_def.get("default_role")
                        or "discovery"
                    ),
                    evidence_type=str(provider_def["evidence_type"]),
                    collection_priority=priority,
                    query_strategy=(
                        str(policy["query_strategy"])
                        if policy.get("query_strategy") is not None
                        else None
                    ),
                )
            )

        routes.sort(key=lambda route: (-route.collection_priority, route.provider))
        return tuple(routes)


def classify_direction(technology_direction: str) -> tuple[str, float, tuple[str, ...]]:
    normalized = _normalize(technology_direction)
    scores: dict[str, float] = {profile: 0.0 for profile in _PROFILE_SIGNALS}
    matches: dict[str, list[str]] = {profile: [] for profile in _PROFILE_SIGNALS}

    for profile, signals in _PROFILE_SIGNALS.items():
        for signal in signals:
            if _signal_matches(normalized, signal):
                weight = min(1.0 + len(signal) / 24.0, 2.0)
                scores[profile] += weight
                matches[profile].append(signal)

    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_profile, best_score = ranked[0]
    second_score = ranked[1][1]

    if best_score == 0:
        return "mixed", 0.25, ()

    if second_score > 0 and second_score >= best_score * 0.8:
        combined_matches = tuple(
            sorted(
                set(matches[ranked[0][0]] + matches[ranked[1][0]]),
                key=lambda value: (-len(value), value),
            )
        )
        return "mixed", 0.55, combined_matches

    margin = best_score - second_score
    confidence = min(0.95, 0.55 + 0.12 * best_score + 0.06 * margin)
    matched_signals = tuple(
        sorted(set(matches[best_profile]), key=lambda value: (-len(value), value))
    )
    return best_profile, round(confidence, 3), matched_signals


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.casefold().replace("-", " ")).strip()


def _signal_matches(normalized: str, signal: str) -> bool:
    needle = _normalize(signal)
    if len(needle) <= 3:
        return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized) is not None
    return needle in normalized


def _validate_config(config: dict[str, Any]) -> dict[str, Any]:
    providers = config.get("providers")
    profiles = config.get("profiles")
    if not isinstance(providers, dict) or not providers:
        raise ValueError("source config must define providers")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError("source config must define profiles")

    for provider_id, provider in providers.items():
        if not isinstance(provider_id, str) or not provider_id.strip():
            raise ValueError("provider id must be a non-empty string")
        if not isinstance(provider, dict):
            raise ValueError(f"provider definition must be object: {provider_id}")
        evidence_type = provider.get("evidence_type")
        if not isinstance(evidence_type, str) or not evidence_type:
            raise ValueError(f"provider missing evidence_type: {provider_id}")

    missing_profiles = SUPPORTED_PROFILES.difference(profiles)
    if missing_profiles:
        raise ValueError(
            "source config missing profiles: " + ", ".join(sorted(missing_profiles))
        )

    return config
