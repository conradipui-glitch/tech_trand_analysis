from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence
from urllib.parse import quote

import httpx


_TOKEN_RE = re.compile(r"(?u)\b[\w-]+\b")


class GitHubHistoryProtocolError(RuntimeError):
    """Raised when GitHub returns a payload that cannot be safely interpreted."""


@dataclass(frozen=True, slots=True)
class GitHubHistoryQuery:
    repository: str
    technology_direction: str
    source_profile: str
    aliases: tuple[str, ...]
    context_terms: tuple[str, ...] = ()
    distinctive_terms: tuple[str, ...] = ()
    query_id: str | None = None

    def __post_init__(self) -> None:
        if "/" not in self.repository or self.repository.startswith("/") or self.repository.endswith("/"):
            raise ValueError("repository must be owner/name")
        if not self.technology_direction.strip():
            raise ValueError("technology_direction must be non-empty")
        if not self.source_profile.strip():
            raise ValueError("source_profile must be non-empty")
        if not any(str(value).strip() for value in (*self.aliases, *self.distinctive_terms)):
            raise ValueError("at least one alias or distinctive term is required")


@dataclass(frozen=True, slots=True)
class VerifiedGitEvent:
    repository: str
    event_kind: str
    external_id: str
    occurred_at: str
    title: str
    url: str
    matched_terms: tuple[str, ...]
    source_endpoint: str

    def to_observation(
        self,
        query: GitHubHistoryQuery,
        *,
        observed_at: datetime | None = None,
    ) -> dict[str, Any]:
        observed = (observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
        owner, _ = self.repository.split("/", 1)
        event_key = f"{self.event_kind}:{self.external_id}"
        return {
            "schema_version": "0.2.0",
            "observation_id": f"github:{self.repository}:{event_key}",
            "provider": "github",
            "evidence_type": "implementation",
            "artifact_kind": self.event_kind,
            "external_id": f"{self.repository}:{event_key}",
            "canonical_url": self.url,
            "title": self.title,
            "text": self.title,
            "published_at": self.occurred_at,
            "updated_at": None,
            "observed_at": _iso_z(observed),
            "language": "en",
            "actors": [
                {
                    "name": owner,
                    "kind": "organization",
                    "external_id": owner,
                    "country": None,
                }
            ],
            "source_topics": list(dict.fromkeys([query.technology_direction, *self.matched_terms])),
            "classifications": [],
            "metrics": {
                "historical_timestamp_verified": True,
                "event_kind": self.event_kind,
            },
            "relationships": [
                {
                    "type": "belongs_to_repository",
                    "target_id": f"github:{self.repository}",
                }
            ],
            "quality_flags": {
                "historical_timestamp_verified": True,
                "mutable_repository_metadata_used_for_timestamp": False,
            },
            "fingerprints": {
                "canonical_key": f"github:{self.repository}:{event_key}",
                "content_hash": None,
                "simhash": None,
            },
            "collection_context": {
                "technology_direction": query.technology_direction,
                "source_profile": query.source_profile,
                "query_id": query.query_id,
                "matched_terms": list(self.matched_terms),
            },
            "rights": {
                "license": None,
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
                "collector": "github_history",
                "collector_version": "0.1.0",
                "request_id": None,
                "source_endpoint": self.source_endpoint,
            },
        }


class GitHubHistoryClient:
    """Find stable historical implementation events for an already-known candidate.

    Repository ``created_at`` and today's repository description are deliberately not
    used as technology timestamps. Only timestamped commit/release/tag events whose
    own text passes the candidate relevance gate are eligible.
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

    def __enter__(self) -> "GitHubHistoryClient":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def verify_earliest(self, query: GitHubHistoryQuery) -> VerifiedGitEvent | None:
        events = [
            *self._search_commits(query),
            *self._search_releases(query),
            *self._search_tags(query),
        ]
        if not events:
            return None
        return min(events, key=lambda event: _parse_time(event.occurred_at))

    def _search_commits(self, query: GitHubHistoryQuery) -> list[VerifiedGitEvent]:
        events: dict[str, VerifiedGitEvent] = {}
        for search_term in _search_terms(query):
            params = {
                "q": f'"{search_term}" repo:{query.repository}',
                "sort": "committer-date",
                "order": "asc",
                "per_page": "20",
            }
            payload = self._get_json("/search/commits", params=params)
            if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
                raise GitHubHistoryProtocolError("commit search payload must contain items[]")
            for item in payload["items"]:
                if not isinstance(item, dict):
                    continue
                commit = item.get("commit")
                if not isinstance(commit, dict):
                    continue
                message = str(commit.get("message") or "").strip()
                matched = _matched_terms(message, query)
                if not matched:
                    continue
                sha = str(item.get("sha") or "").strip()
                html_url = str(item.get("html_url") or "").strip()
                occurred_at = _commit_time(commit)
                if not sha or not html_url or occurred_at is None:
                    continue
                event = VerifiedGitEvent(
                    repository=query.repository,
                    event_kind="commit",
                    external_id=sha,
                    occurred_at=occurred_at,
                    title=_first_line(message) or f"commit {sha[:12]}",
                    url=html_url,
                    matched_terms=matched,
                    source_endpoint="GET /search/commits",
                )
                events[sha] = event
        return list(events.values())

    def _search_releases(self, query: GitHubHistoryQuery) -> list[VerifiedGitEvent]:
        payload = self._get_json(f"/repos/{query.repository}/releases", params={"per_page": "100"})
        if not isinstance(payload, list):
            raise GitHubHistoryProtocolError("releases payload must be a list")
        events: list[VerifiedGitEvent] = []
        for item in payload:
            if not isinstance(item, dict) or bool(item.get("draft")):
                continue
            text = " ".join(
                str(item.get(key) or "").strip()
                for key in ("name", "tag_name", "body")
            ).strip()
            matched = _matched_terms(text, query)
            if not matched:
                continue
            occurred_at = str(item.get("published_at") or item.get("created_at") or "").strip()
            url = str(item.get("html_url") or "").strip()
            external_id = str(item.get("id") or item.get("tag_name") or "").strip()
            if not occurred_at or not url or not external_id:
                continue
            events.append(
                VerifiedGitEvent(
                    repository=query.repository,
                    event_kind="release",
                    external_id=external_id,
                    occurred_at=_canonical_time(occurred_at),
                    title=str(item.get("name") or item.get("tag_name") or external_id),
                    url=url,
                    matched_terms=matched,
                    source_endpoint=f"GET /repos/{query.repository}/releases",
                )
            )
        return events

    def _search_tags(self, query: GitHubHistoryQuery) -> list[VerifiedGitEvent]:
        payload = self._get_json(f"/repos/{query.repository}/tags", params={"per_page": "100"})
        if not isinstance(payload, list):
            raise GitHubHistoryProtocolError("tags payload must be a list")
        events: list[VerifiedGitEvent] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            tag_name = str(item.get("name") or "").strip()
            matched = _matched_terms(tag_name, query)
            commit_ref = item.get("commit")
            if not matched or not isinstance(commit_ref, dict):
                continue
            sha = str(commit_ref.get("sha") or "").strip()
            if not sha:
                continue
            detail = self._get_json(f"/repos/{query.repository}/commits/{quote(sha, safe='')}")
            if not isinstance(detail, dict) or not isinstance(detail.get("commit"), dict):
                continue
            occurred_at = _commit_time(detail["commit"])
            if occurred_at is None:
                continue
            events.append(
                VerifiedGitEvent(
                    repository=query.repository,
                    event_kind="tag",
                    external_id=tag_name,
                    occurred_at=occurred_at,
                    title=tag_name,
                    url=f"https://github.com/{query.repository}/releases/tag/{quote(tag_name, safe='')}",
                    matched_terms=matched,
                    source_endpoint=f"GET /repos/{query.repository}/tags",
                )
            )
        return events

    def _get_json(self, path: str, *, params: dict[str, str] | None = None) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.client.get(path, params=params)
                if response.status_code in {429, 502, 503, 504}:
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after and retry_after.isdigit() else min(2**attempt, 8)
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(min(2**attempt, 8))
        raise GitHubHistoryProtocolError(f"GitHub request failed for {path}: {last_error}")


def _search_terms(query: GitHubHistoryQuery) -> tuple[str, ...]:
    values = [*query.distinctive_terms, *query.aliases]
    return tuple(dict.fromkeys(value.strip() for value in values if value.strip()))


def _matched_terms(text: str, query: GitHubHistoryQuery) -> tuple[str, ...]:
    normalized_text = _normalize(text)
    tokens = set(_tokens(text))
    context_hits = [term for term in query.context_terms if _term_hit(term, normalized_text, tokens)]
    matched: list[str] = []

    for term in query.distinctive_terms:
        if _term_hit(term, normalized_text, tokens):
            matched.append(term)

    for alias in query.aliases:
        alias_tokens = _tokens(alias)
        if not alias_tokens:
            continue
        if len(alias_tokens) >= 2:
            if _normalize(alias) in normalized_text:
                matched.append(alias)
        elif alias_tokens[0] in tokens and context_hits:
            matched.append(alias)

    if not matched:
        return ()
    matched.extend(context_hits)
    return tuple(dict.fromkeys(matched))


def _term_hit(term: str, normalized_text: str, tokens: set[str]) -> bool:
    term_tokens = _tokens(term)
    if not term_tokens:
        return False
    if len(term_tokens) == 1:
        return term_tokens[0] in tokens
    return _normalize(term) in normalized_text


def _tokens(value: str) -> list[str]:
    return [token.casefold().strip("-") for token in _TOKEN_RE.findall(str(value)) if token.strip("-")]


def _normalize(value: str) -> str:
    return " ".join(_tokens(value))


def _commit_time(commit: dict[str, Any]) -> str | None:
    for role in ("committer", "author"):
        payload = commit.get(role)
        if isinstance(payload, dict):
            value = str(payload.get("date") or "").strip()
            if value:
                return _canonical_time(value)
    return None


def _canonical_time(value: str) -> str:
    parsed = _parse_time(value)
    return _iso_z(parsed)


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _first_line(value: str) -> str:
    return value.splitlines()[0].strip() if value else ""
