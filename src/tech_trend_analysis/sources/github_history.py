from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
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
    evidence_text: str | None = None

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
            "text": self.evidence_text or self.title,
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

    def candidate_events(
        self,
        query: GitHubHistoryQuery,
        *,
        max_candidates: int = 24,
        commit_pages_per_term: int = 2,
        max_diff_checks: int = 6,
    ) -> tuple[VerifiedGitEvent, ...]:
        """Bounded chronological candidate pool, NOT proof of first-ever use.

        This broader retrieval intentionally includes ambiguous short aliases.
        The caller MUST apply technology-specific event-local verification and
        similarity. Never treat a lexical hit as historical implementation.
        """
        if not 1 <= max_candidates <= 100:
            raise ValueError("max_candidates must be 1..100")
        if not 1 <= commit_pages_per_term <= 4:
            raise ValueError("commit_pages_per_term must be 1..4")
        if not 0 <= max_diff_checks <= 12:
            raise ValueError("max_diff_checks must be 0..12")
        all_events = [
            *self._search_commits(query, pages=commit_pages_per_term, recall_only=True),
            *self._search_releases(query),
            *self._search_tags(query),
        ]
        # Stable de-dup across aliases. Sort by actual event time, never by
        # API result order or mutable repository metadata.
        unique: dict[tuple[str, str], VerifiedGitEvent] = {}
        for event in all_events:
            unique.setdefault((event.event_kind, event.external_id), event)
        ordered = sorted(
            unique.values(),
            key=lambda event: (_parse_time(event.occurred_at), event.event_kind, event.external_id),
        )[:max_candidates]
        enriched: list[VerifiedGitEvent] = []
        diff_checks = 0
        for event in ordered:
            # A short, ambiguous commit message can be disambiguated using
            # the immutable patch/filenames belonging to the very same SHA.
            if event.event_kind == "commit" and diff_checks < max_diff_checks and len(event.evidence_text or "") < 180:
                diff_checks += 1
                enriched.append(self._enrich_commit_patch(query.repository, event))
            else:
                enriched.append(event)
        return tuple(enriched)

    def _enrich_commit_patch(self, repository: str, event: VerifiedGitEvent) -> VerifiedGitEvent:
        payload = self._get_json(f"/repos/{repository}/commits/{quote(event.external_id, safe='')}")
        if not isinstance(payload, dict) or not isinstance(payload.get("files"), list):
            return event
        # Restrict to actual added lines in source files, avoiding removed or
        # comment-only context and unrelated release note text.
        snippets: list[str] = []
        for item in payload["files"][:20]:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("filename") or "")
            if not filename.endswith((".py", ".ts", ".tsx", ".js", ".rs", ".cpp", ".c", ".go")):
                continue
            patch = str(item.get("patch") or "")
            added = [
                line[1:].strip() for line in patch.splitlines()
                if line.startswith("+") and not line.startswith("+++")
                and any(token in line.casefold() for token in ("lora", "loralib", "ragretriever", "retrieval"))
                and not line[1:].lstrip().startswith(("#", "//", "*"))
            ]
            if added:
                snippets.append(f"FILE {filename}\n" + "\n".join(added[:8]))
            if len(snippets) >= 3:
                break
        if not snippets:
            return event
        return VerifiedGitEvent(
            repository=event.repository,
            event_kind=event.event_kind,
            external_id=event.external_id,
            occurred_at=event.occurred_at,
            title=event.title,
            url=event.url,
            matched_terms=event.matched_terms,
            source_endpoint=event.source_endpoint,
            evidence_text=((event.evidence_text or event.title) + "\nGIT_PATCH_ADDED_LINES\n" + "\n".join(snippets))[:4000],
        )

    def _search_commits(
        self,
        query: GitHubHistoryQuery,
        *,
        pages: int = 1,
        recall_only: bool = False,
    ) -> list[VerifiedGitEvent]:
        events: dict[str, VerifiedGitEvent] = {}
        for search_term in _search_terms(query):
            for page in range(1, pages + 1):
                params = {
                    "q": f'"{search_term}" repo:{query.repository}',
                    "sort": "committer-date",
                    "order": "asc",
                    "per_page": "20",
                    "page": str(page),
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
                    if not matched and recall_only:
                        # Recall expansion only; never an acceptance. Even LoRa
                        # radio is allowed into this candidate pool for later rejection.
                        normalized = _normalize(message)
                        tokens = set(_tokens(message))
                        matched = tuple(
                            alias for alias in query.aliases
                            if len(_tokens(alias)) == 1 and _tokens(alias)[0] in tokens
                        )
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
                        evidence_text=message[:4000],
                    )
                    events[sha] = event
                if len(payload["items"]) < 20:
                    break
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
            occurred_at = str(item.get("published_at") or "").strip()
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
                    evidence_text=text[:4000],
                )
            )
        return events

    def _search_tags(self, query: GitHubHistoryQuery) -> list[VerifiedGitEvent]:
        # GitHub's listing of lightweight tags has no creation timestamp.
        # The referenced commit date can be YEARS older than the tag; using
        # it as the tag's publication date would invent pre-origin evidence.
        # Until annotated-tag tagger dates are explicitly validated, fail
        # closed and rely on actual commits / published releases.
        return []

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
    # GitHub commit search is case-insensitive; deduplicate LoRA/lora query
    # strings to save API quota, while preserving preferred distinctive term.
    values = [*query.distinctive_terms, *query.aliases]
    chosen: dict[str, str] = {}
    for value in values:
        term = value.strip()
        if term:
            chosen.setdefault(term.casefold(), term)
    return tuple(chosen.values())


def _matched_terms(text: str, query: GitHubHistoryQuery) -> tuple[str, ...]:
    normalized_text = _normalize(text)
    tokens = set(_tokens(text))
    context_hits = [term for term in query.context_terms if _term_hit(term, normalized_text, tokens)]
    matched: list[str] = []

    for term in query.distinctive_terms:
        if _distinctive_hit(term, text):
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


def _distinctive_hit(term: str, text: str) -> bool:
    raw_term_tokens = [token.strip("-") for token in _TOKEN_RE.findall(str(term)) if token.strip("-")]
    raw_text_tokens = [token.strip("-") for token in _TOKEN_RE.findall(str(text)) if token.strip("-")]
    if not raw_term_tokens:
        return False
    case_sensitive = any(char.islower() for char in term) and any(char.isupper() for char in term)
    if len(raw_term_tokens) == 1:
        if case_sensitive:
            return raw_term_tokens[0] in set(raw_text_tokens)
        return raw_term_tokens[0].casefold() in {token.casefold() for token in raw_text_tokens}
    if case_sensitive:
        return " ".join(raw_term_tokens) in " ".join(raw_text_tokens)
    return _normalize(term) in _normalize(text)


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
