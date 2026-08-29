from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx


class GitHubProtocolError(RuntimeError):
    """Raised when GitHub repository search cannot be safely interpreted."""


@dataclass(frozen=True, slots=True)
class GitHubQuery:
    technology_direction: str
    source_profile: str
    query_text: str
    query_id: str
    per_page: int = 50
    max_pages: int = 2
    sort: str = "updated"
    order: str = "desc"
    include_forks: bool = False
    include_archived: bool = False

    def __post_init__(self) -> None:
        if not self.technology_direction.strip():
            raise ValueError("technology_direction must be non-empty")
        if not self.source_profile.strip():
            raise ValueError("source_profile must be non-empty")
        if not self.query_text.strip():
            raise ValueError("query_text must be non-empty")
        if not self.query_id.strip():
            raise ValueError("query_id must be non-empty")
        if not 1 <= self.per_page <= 100:
            raise ValueError("per_page must be 1..100")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        if self.sort not in {"stars", "forks", "help-wanted-issues", "updated"}:
            raise ValueError("unsupported GitHub repository sort")
        if self.order not in {"asc", "desc"}:
            raise ValueError("order must be asc or desc")


@dataclass(frozen=True, slots=True)
class GitHubRepositoryCandidate:
    full_name: str
    name: str
    html_url: str
    description: str | None
    owner_login: str
    owner_id: str | None
    topics: tuple[str, ...]
    language: str | None
    license_spdx: str | None
    stars: int
    forks: int
    open_issues: int
    watchers: int
    size_kb: int
    created_at: str | None
    updated_at: str | None
    pushed_at: str | None
    archived: bool
    fork: bool


class GitHubAdapter:
    """Present-day GitHub repository discovery.

    This adapter deliberately does **not** backdate a technology to repository
    ``created_at``. Repository metadata is mutable, so discovery observations use
    ``observed_at`` as their event time and leave ``published_at`` empty. Historical
    first-seen is resolved separately by ``GitHubHistoryClient`` using relevant
    commit/release/tag timestamps.
    """

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = "https://api.github.com",
        timeout_seconds: float = 20.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tech-trend-analysis/0.1",
        }
        if token and token.strip():
            headers["Authorization"] = f"Bearer {token.strip()}"
        self.max_retries = max_retries
        self.client = httpx.Client(
            base_url=base_url,
            headers=headers,
            timeout=timeout_seconds,
            transport=transport,
        )

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "GitHubAdapter":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def iter_candidates(self, query: GitHubQuery) -> Iterator[GitHubRepositoryCandidate]:
        seen: set[str] = set()
        for page in range(1, query.max_pages + 1):
            payload = self._get_json(
                "/search/repositories",
                params={
                    "q": query.query_text,
                    "sort": query.sort,
                    "order": query.order,
                    "per_page": str(query.per_page),
                    "page": str(page),
                },
            )
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise GitHubProtocolError("repository search payload must contain items[]")
            items = payload["items"]
            if not items:
                break
            for raw in items:
                candidate = _map_candidate(raw)
                if candidate.full_name in seen:
                    continue
                seen.add(candidate.full_name)
                if candidate.fork and not query.include_forks:
                    continue
                if candidate.archived and not query.include_archived:
                    continue
                yield candidate
            if len(items) < query.per_page:
                break

    def collect(
        self,
        query: GitHubQuery,
        *,
        observed_at: datetime | None = None,
    ) -> list[dict[str, Any]]:
        observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        return [self.to_observation(candidate, query, observed_at=observed) for candidate in self.iter_candidates(query)]

    def to_observation(
        self,
        candidate: GitHubRepositoryCandidate,
        query: GitHubQuery,
        *,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        searchable = " ".join(
            value
            for value in [candidate.name, candidate.description or "", *candidate.topics]
            if value
        )
        matched_terms = _matched_query_terms(query.query_text, searchable)
        return {
            "schema_version": "0.2.0",
            "observation_id": f"github:{candidate.full_name}",
            "provider": "github",
            "evidence_type": "implementation",
            "artifact_kind": "repository",
            "external_id": candidate.full_name,
            "canonical_url": candidate.html_url,
            "title": candidate.name,
            "text": candidate.description,
            # CRITICAL: current mutable metadata cannot prove when the technology
            # first appeared. Do not put repository created_at here.
            "published_at": None,
            "updated_at": candidate.updated_at,
            "observed_at": _iso_z(observed),
            "language": candidate.language,
            "actors": [
                {
                    "name": candidate.owner_login,
                    "kind": "organization",
                    "external_id": candidate.owner_id or candidate.owner_login,
                    "country": None,
                }
            ],
            "source_topics": list(candidate.topics),
            "classifications": [],
            "metrics": {
                "stars": candidate.stars,
                "forks": candidate.forks,
                "open_issues": candidate.open_issues,
                "watchers": candidate.watchers,
                "repository_size_kb": candidate.size_kb,
                "repository_created_at": candidate.created_at,
                "repository_pushed_at": candidate.pushed_at,
                "historical_timestamp_verified": False,
            },
            "relationships": [],
            "quality_flags": {
                "archived": candidate.archived,
                "fork": candidate.fork,
                "historical_timestamp_verified": False,
                "time_semantics": "current_snapshot_only",
            },
            "fingerprints": {
                "canonical_key": f"github:{candidate.full_name}",
                "content_hash": None,
                "simhash": None,
            },
            "collection_context": {
                "technology_direction": query.technology_direction,
                "source_profile": query.source_profile,
                "query_id": query.query_id,
                "matched_terms": matched_terms,
            },
            "rights": {
                "license": candidate.license_spdx,
                "access_level": "public",
                "reuse_notes": None,
            },
            "analysis": {
                "relevance": None,
                "novelty": None,
                "cluster_id": None,
                "embedding_ref": None,
                "technology_labels": [],
            },
            "raw_ref": None,
            "provenance": {
                "collector": "github_rest",
                "collector_version": "0.1.0",
                "request_id": None,
                "source_endpoint": "GET /search/repositories",
            },
        }

    def _get_json(self, path: str, *, params: dict[str, str]) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(path, params=params)
                if response.status_code in {429, 502, 503, 504}:
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    delay = _retry_delay(response, attempt)
                    time.sleep(delay)
                    continue
                if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    delay = _retry_delay(response, attempt)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise GitHubProtocolError(f"GitHub request failed for {path}: {last_error}")


def _map_candidate(raw: Any) -> GitHubRepositoryCandidate:
    if not isinstance(raw, dict):
        raise GitHubProtocolError("repository item must be an object")
    full_name = _required_str(raw, "full_name")
    name = _required_str(raw, "name")
    html_url = _required_str(raw, "html_url")
    owner = raw.get("owner")
    if not isinstance(owner, dict):
        raise GitHubProtocolError(f"repository {full_name} missing owner")
    owner_login = _required_str(owner, "login")
    owner_id = str(owner.get("id")) if owner.get("id") is not None else None
    license_payload = raw.get("license")
    license_spdx = None
    if isinstance(license_payload, dict):
        value = license_payload.get("spdx_id")
        if isinstance(value, str) and value.strip() and value != "NOASSERTION":
            license_spdx = value.strip()

    topics = raw.get("topics")
    normalized_topics = tuple(
        dict.fromkeys(
            str(value).strip()
            for value in topics
            if isinstance(value, str) and value.strip()
        )
    ) if isinstance(topics, list) else ()

    return GitHubRepositoryCandidate(
        full_name=full_name,
        name=name,
        html_url=html_url,
        description=_optional_str(raw.get("description")),
        owner_login=owner_login,
        owner_id=owner_id,
        topics=normalized_topics,
        language=_optional_str(raw.get("language")),
        license_spdx=license_spdx,
        stars=_nonnegative_int(raw.get("stargazers_count")),
        forks=_nonnegative_int(raw.get("forks_count")),
        open_issues=_nonnegative_int(raw.get("open_issues_count")),
        watchers=_nonnegative_int(raw.get("subscribers_count", raw.get("watchers_count"))),
        size_kb=_nonnegative_int(raw.get("size")),
        created_at=_optional_str(raw.get("created_at")),
        updated_at=_optional_str(raw.get("updated_at")),
        pushed_at=_optional_str(raw.get("pushed_at")),
        archived=bool(raw.get("archived")),
        fork=bool(raw.get("fork")),
    )


def _matched_query_terms(query_text: str, searchable: str) -> list[str]:
    haystack = searchable.casefold()
    terms = [
        token.casefold()
        for token in re.findall(r"(?u)\b[\w-]{3,}\b", query_text)
        if token.casefold() not in {"and", "not", "the", "with", "from", "language"}
    ]
    return list(dict.fromkeys(term for term in terms if term in haystack))[:12]


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after and retry_after.isdigit():
        return min(float(retry_after), 60.0)
    reset = response.headers.get("X-RateLimit-Reset")
    if reset and reset.isdigit():
        now = time.time()
        return max(0.5, min(float(reset) - now + 0.5, 60.0))
    return float(min(2**attempt, 8))


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GitHubProtocolError(f"{key} must be a non-empty string")
    return value.strip()


def _optional_str(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError) as exc:
        raise GitHubProtocolError(f"expected integer metric, got {value!r}") from exc


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
