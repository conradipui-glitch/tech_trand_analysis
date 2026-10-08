"""B-037 independent evidence units: distinguish activity from independent adoption.

Raw Observations stay intact for audit. A GitHub repository snapshot and all
dated commit/release events in that repository count as at most ONE independent
implementation for scoring. Among verified dated events the EARLIEST wins;
otherwise current discovery is represented at observed_at (not repo created_at).

Supporting module maintenance MUST NOT be fed here as a separate adoption.
This module never claims that one GitHub repository equals one unique company.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

UNIT_POLICY_VERSION = "0.1.0"


@dataclass(frozen=True, slots=True)
class IndependentEvidenceUnit:
    unit_key: str
    observation_id: str
    provider: str
    evidence_type: str
    event_time: str
    actor_keys: tuple[str, ...]
    historical_verified: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_key": self.unit_key,
            "observation_id": self.observation_id,
            "provider": self.provider,
            "evidence_type": self.evidence_type,
            "event_time": self.event_time,
            "actor_keys": list(self.actor_keys),
            "historical_verified": self.historical_verified,
        }


def _repo_key(observation: Mapping[str, Any]) -> str | None:
    if observation.get("provider") != "github":
        return None
    artifact = str(observation.get("artifact_kind") or "")
    if artifact == "repository":
        value = observation.get("external_id")
        if not isinstance(value, str) or "/" not in value:
            oid = observation.get("observation_id")
            value = oid[7:] if isinstance(oid, str) and oid.startswith("github:") else None
    else:
        value = None
        for rel in observation.get("relationships") or ():
            if (isinstance(rel, Mapping) and rel.get("type") == "belongs_to_repository"
                    and isinstance(rel.get("target_id"), str)
                    and rel["target_id"].startswith("github:")):
                value = rel["target_id"][7:]
                break
        if value is None:
            # An unlinked Git event cannot count as a new independent project.
            raise ValueError("GitHub event lacks belongs_to_repository provenance")
    if not isinstance(value, str) or value.count("/") != 1:
        return None
    owner, name = value.split("/", 1)
    if not owner.strip() or not name.strip():
        return None
    return owner.strip().casefold() + "/" + name.strip().casefold()


def independent_unit(
    observation: Mapping[str, Any],
    *,
    event_time: str,
    actor_keys: set[str],
) -> IndependentEvidenceUnit:
    oid = observation.get("observation_id")
    provider = observation.get("provider")
    evidence = observation.get("evidence_type")
    if not all(isinstance(x, str) and x.strip() for x in (oid, provider, evidence)):
        raise ValueError("Observation missing essential independent-evidence fields")
    repo = _repo_key(observation)
    if provider == "github" and repo:
        flags = observation.get("quality_flags") or {}
        verified = (
            observation.get("artifact_kind") != "repository"
            and isinstance(flags, Mapping)
            and flags.get("historical_timestamp_verified") is True
            and isinstance(observation.get("published_at"), str)
        )
        if verified:
            timestamp = event_time
        else:
            # Current GitHub repository metadata is mutable and has no
            # evidence of technology existence at repository created_at.
            observed = observation.get("observed_at")
            if not isinstance(observed, str) or not observed.strip():
                raise ValueError("unverified GitHub discovery must have observed_at")
            timestamp = observed
        # All repos of one owner contribute separate repo units but only ONE
        # independent organization actor. Ignore numeric vs login IDs.
        return IndependentEvidenceUnit(
            unit_key=f"github:repo:{repo}",
            observation_id=oid,
            provider="github",
            evidence_type=evidence,
            event_time=timestamp,
            actor_keys=(f"github:owner:{repo.split('/', 1)[0]}",),
            historical_verified=verified,
        )
    return IndependentEvidenceUnit(
        unit_key=f"observation:{oid}",
        observation_id=oid,
        provider=provider,
        evidence_type=evidence,
        event_time=event_time,
        actor_keys=tuple(sorted(actor_keys)),
    )


def select_representative(
    existing: IndependentEvidenceUnit | None,
    candidate: IndependentEvidenceUnit,
) -> IndependentEvidenceUnit:
    """Order-independent: verified earlier event beats current snapshot."""
    if existing is None:
        return candidate
    if existing.unit_key != candidate.unit_key:
        raise ValueError("cannot compare independent evidence units with different keys")
    if candidate.historical_verified != existing.historical_verified:
        return candidate if candidate.historical_verified else existing
    return min((existing, candidate), key=lambda x: (x.event_time, x.observation_id))
