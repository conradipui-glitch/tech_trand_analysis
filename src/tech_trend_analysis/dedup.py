from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


_TRACKING_PARAMS = {"ref", "source", "fbclid", "gclid"}
_TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class DedupPolicy:
    fuzzy_jaccard_threshold: float = 0.86
    fuzzy_simhash_max_distance: int = 4
    fuzzy_min_tokens: int = 4
    require_actor_overlap_when_both_present: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.fuzzy_jaccard_threshold <= 1:
            raise ValueError("fuzzy_jaccard_threshold must be in [0, 1]")
        if not 0 <= self.fuzzy_simhash_max_distance <= 64:
            raise ValueError("fuzzy_simhash_max_distance must be in [0, 64]")
        if self.fuzzy_min_tokens < 1:
            raise ValueError("fuzzy_min_tokens must be >= 1")


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    observation_id: str
    duplicate_of: str
    reason: str
    similarity: float


@dataclass(frozen=True, slots=True)
class DedupBatchResult:
    unique: list[dict[str, Any]]
    duplicates: list[DuplicateMatch]


@dataclass(slots=True)
class _Candidate:
    observation_id: str
    evidence_type: str
    artifact_kind: str
    title_tokens: frozenset[str]
    simhash: int
    actor_keys: frozenset[str]


class ObservationDeduplicator:
    """Cheap deterministic dedup before embeddings.

    Exact keys collapse the same artifact across provider aliases. Fuzzy matching is
    deliberately conservative and is scoped to the same evidence type + artifact
    kind, so a paper and an implementation repository with the same title remain
    independent evidence.
    """

    def __init__(self, policy: DedupPolicy | None = None) -> None:
        self.policy = policy or DedupPolicy()
        self._exact_index: dict[str, str] = {}
        self._candidates: list[_Candidate] = []

    def add_batch(self, observations: Iterable[dict[str, Any]]) -> DedupBatchResult:
        unique: list[dict[str, Any]] = []
        duplicates: list[DuplicateMatch] = []

        for raw_observation in observations:
            observation = _prepare_observation(raw_observation)
            observation_id = _required_string(observation, "observation_id")

            exact = self._find_exact(observation)
            if exact is not None:
                duplicates.append(
                    DuplicateMatch(
                        observation_id=observation_id,
                        duplicate_of=exact,
                        reason="exact",
                        similarity=1.0,
                    )
                )
                continue

            fuzzy = self._find_fuzzy(observation)
            if fuzzy is not None:
                duplicate_of, similarity = fuzzy
                duplicates.append(
                    DuplicateMatch(
                        observation_id=observation_id,
                        duplicate_of=duplicate_of,
                        reason="fuzzy_title",
                        similarity=similarity,
                    )
                )
                continue

            self._index(observation)
            unique.append(observation)

        return DedupBatchResult(unique=unique, duplicates=duplicates)

    def _find_exact(self, observation: dict[str, Any]) -> str | None:
        for key in _exact_keys(observation):
            existing = self._exact_index.get(key)
            if existing is not None:
                return existing
        return None

    def _find_fuzzy(self, observation: dict[str, Any]) -> tuple[str, float] | None:
        evidence_type = _required_string(observation, "evidence_type")
        artifact_kind = _required_string(observation, "artifact_kind")
        tokens = _title_tokens(_required_string(observation, "title"))
        if len(tokens) < self.policy.fuzzy_min_tokens:
            return None

        simhash_value = _observation_simhash_int(observation)
        actor_keys = _actor_keys(observation)
        best: tuple[str, float] | None = None

        for candidate in self._candidates:
            if candidate.evidence_type != evidence_type:
                continue
            if candidate.artifact_kind != artifact_kind:
                continue
            if len(candidate.title_tokens) < self.policy.fuzzy_min_tokens:
                continue
            if (
                self.policy.require_actor_overlap_when_both_present
                and actor_keys
                and candidate.actor_keys
                and actor_keys.isdisjoint(candidate.actor_keys)
            ):
                continue

            jaccard = _jaccard(tokens, candidate.title_tokens)
            distance = _hamming_distance(simhash_value, candidate.simhash)
            simhash_similarity = 1.0 - (distance / 64.0)

            is_match = (
                jaccard >= self.policy.fuzzy_jaccard_threshold
                and distance <= self.policy.fuzzy_simhash_max_distance
            )
            if not is_match:
                continue

            similarity = min(jaccard, simhash_similarity)
            if best is None or similarity > best[1]:
                best = (candidate.observation_id, similarity)

        return best

    def _index(self, observation: dict[str, Any]) -> None:
        observation_id = _required_string(observation, "observation_id")
        for key in _exact_keys(observation):
            self._exact_index.setdefault(key, observation_id)

        self._candidates.append(
            _Candidate(
                observation_id=observation_id,
                evidence_type=_required_string(observation, "evidence_type"),
                artifact_kind=_required_string(observation, "artifact_kind"),
                title_tokens=_title_tokens(_required_string(observation, "title")),
                simhash=_observation_simhash_int(observation),
                actor_keys=_actor_keys(observation),
            )
        )


def _prepare_observation(raw: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise TypeError("observation must be a dict")
    observation = dict(raw)
    _required_string(observation, "observation_id")
    _required_string(observation, "provider")
    _required_string(observation, "external_id")
    _required_string(observation, "evidence_type")
    _required_string(observation, "artifact_kind")
    title = _required_string(observation, "title")

    fingerprints = observation.get("fingerprints")
    if not isinstance(fingerprints, dict):
        fingerprints = {}
    else:
        fingerprints = dict(fingerprints)

    normalized_body = _normalize_text(
        " ".join(
            part
            for part in [title, observation.get("text") if isinstance(observation.get("text"), str) else None]
            if part
        )
    )
    if not fingerprints.get("content_hash") and normalized_body:
        fingerprints["content_hash"] = hashlib.sha256(
            normalized_body.encode("utf-8")
        ).hexdigest()
    if not fingerprints.get("simhash"):
        fingerprints["simhash"] = f"{_simhash(_title_tokens(title)):016x}"

    observation["fingerprints"] = fingerprints
    return observation


def _exact_keys(observation: dict[str, Any]) -> list[str]:
    keys: list[str] = []
    fingerprints = observation.get("fingerprints")
    if isinstance(fingerprints, dict):
        canonical_key = fingerprints.get("canonical_key")
        if isinstance(canonical_key, str) and canonical_key.strip():
            keys.append(f"canonical:{canonical_key.strip().casefold()}")
        content_hash = fingerprints.get("content_hash")
        if isinstance(content_hash, str) and content_hash.strip():
            keys.append(f"content:{content_hash.strip().casefold()}")

    provider = _required_string(observation, "provider")
    external_id = _required_string(observation, "external_id")
    keys.append(f"provider-id:{provider.casefold()}:{external_id.casefold()}")

    url = observation.get("canonical_url")
    if isinstance(url, str) and url.strip():
        normalized_url = _normalize_url(url)
        if normalized_url:
            keys.append(f"url:{normalized_url}")
        doi = _normalize_doi(url)
        if doi:
            keys.append(f"doi:{doi}")

    return list(dict.fromkeys(keys))


def _normalize_url(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    try:
        parts = urlsplit(raw)
    except ValueError:
        return raw.casefold().rstrip("/")
    if not parts.scheme or not parts.netloc:
        return raw.casefold().rstrip("/")

    filtered_query = []
    for key, val in parse_qsl(parts.query, keep_blank_values=True):
        lowered = key.casefold()
        if lowered.startswith("utm_") or lowered in _TRACKING_PARAMS:
            continue
        filtered_query.append((key, val))

    path = parts.path.rstrip("/") or "/"
    normalized = urlunsplit(
        (
            parts.scheme.casefold(),
            parts.netloc.casefold(),
            path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )
    return normalized


def _normalize_doi(value: str) -> str | None:
    candidate = value.strip().casefold()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if candidate.startswith(prefix):
            candidate = candidate[len(prefix):]
            break
    if candidate.startswith("10.") and "/" in candidate:
        return candidate.rstrip("/ .")
    return None


def _title_tokens(title: str) -> frozenset[str]:
    normalized = _normalize_text(title)
    return frozenset(token for token in _TOKEN_RE.findall(normalized) if token)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = normalized.replace("-", " ").replace("_", " ")
    return " ".join(_TOKEN_RE.findall(normalized))


def _actor_keys(observation: dict[str, Any]) -> frozenset[str]:
    actors = observation.get("actors")
    if not isinstance(actors, list):
        return frozenset()
    result: set[str] = set()
    for actor in actors:
        if not isinstance(actor, dict):
            continue
        external_id = actor.get("external_id")
        name = actor.get("name")
        if isinstance(external_id, str) and external_id.strip():
            result.add(f"id:{external_id.strip().casefold()}")
        elif isinstance(name, str) and name.strip():
            result.add(f"name:{_normalize_text(name)}")
    return frozenset(result)


def _observation_simhash_int(observation: dict[str, Any]) -> int:
    fingerprints = observation.get("fingerprints")
    if isinstance(fingerprints, dict):
        value = fingerprints.get("simhash")
        if isinstance(value, str):
            try:
                return int(value, 16)
            except ValueError:
                pass
    return _simhash(_title_tokens(_required_string(observation, "title")))


def _simhash(tokens: Iterable[str]) -> int:
    vector = [0] * 64
    token_list = list(tokens)
    if not token_list:
        return 0
    for token in token_list:
        digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
        value = int.from_bytes(digest, "big")
        for bit in range(64):
            vector[bit] += 1 if value & (1 << bit) else -1
    result = 0
    for bit, weight in enumerate(vector):
        if weight >= 0:
            result |= 1 << bit
    return result


def _hamming_distance(left: int, right: int) -> int:
    return (left ^ right).bit_count()


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    union = left | right
    if not union:
        return 1.0
    return len(left & right) / len(union)


def _required_string(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()
