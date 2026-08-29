from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator

import httpx

OPENALEX_BASE_URL = "https://api.openalex.org"
COLLECTOR_VERSION = "0.1.0"


class OpenAlexProtocolError(RuntimeError):
    """Raised when OpenAlex returns a response that violates the expected protocol."""


@dataclass(frozen=True, slots=True)
class OpenAlexQuery:
    technology_direction: str
    source_profile: str
    from_date: date
    to_date: date
    query_text: str | None = None
    query_id: str | None = None
    per_page: int = 100
    max_pages: int = 10
    extra_filters: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.technology_direction.strip():
            raise ValueError("technology_direction must not be empty")
        if not self.source_profile.strip():
            raise ValueError("source_profile must not be empty")
        if self.from_date > self.to_date:
            raise ValueError("from_date must be <= to_date")
        if not 1 <= self.per_page <= 200:
            raise ValueError("per_page must be between 1 and 200")
        if self.max_pages < 1:
            raise ValueError("max_pages must be >= 1")

    @property
    def effective_query_text(self) -> str:
        return (self.query_text or self.technology_direction).strip()

    @property
    def effective_query_id(self) -> str:
        if self.query_id:
            return self.query_id
        raw = "|".join(
            [
                self.technology_direction.strip().lower(),
                self.source_profile.strip().lower(),
                self.from_date.isoformat(),
                self.to_date.isoformat(),
                self.effective_query_text.lower(),
                ",".join(self.extra_filters),
            ]
        )
        digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
        return f"openalex:{digest}"


class OpenAlexAdapter:
    """Normalize OpenAlex Works into the project's Observation contract."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        email: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        user_agent: str = "tech-trend-analysis/0.1",
    ) -> None:
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0")
        self.api_key = api_key
        self.email = email
        self.timeout = timeout
        self.max_retries = max_retries
        self.user_agent = user_agent
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(
            base_url=OPENALEX_BASE_URL,
            timeout=timeout,
            headers={"User-Agent": user_agent},
        )

    async def __aenter__(self) -> "OpenAlexAdapter":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    async def iter_recent(self, query: OpenAlexQuery) -> AsyncIterator[dict[str, Any]]:
        cursor = "*"
        observed_at = _utc_now_iso()

        for _page_number in range(query.max_pages):
            params = self._build_params(query, cursor=cursor)
            payload = await self._get_json("/works", params=params)

            results = payload.get("results")
            meta = payload.get("meta")
            if not isinstance(results, list):
                raise OpenAlexProtocolError("OpenAlex response missing list 'results'")
            if not isinstance(meta, dict):
                raise OpenAlexProtocolError("OpenAlex response missing object 'meta'")

            for work in results:
                if not isinstance(work, dict):
                    continue
                yield self.to_observation(
                    work,
                    query=query,
                    observed_at=observed_at,
                )

            next_cursor = meta.get("next_cursor")
            if not results or not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor

    async def collect_recent(self, query: OpenAlexQuery) -> list[dict[str, Any]]:
        return [observation async for observation in self.iter_recent(query)]

    def _build_params(self, query: OpenAlexQuery, *, cursor: str) -> dict[str, str | int]:
        filters = [
            f"from_publication_date:{query.from_date.isoformat()}",
            f"to_publication_date:{query.to_date.isoformat()}",
            *query.extra_filters,
        ]
        params: dict[str, str | int] = {
            "search": query.effective_query_text,
            "filter": ",".join(filters),
            "per-page": query.per_page,
            "cursor": cursor,
        }
        if self.api_key:
            params["api_key"] = self.api_key
        if self.email:
            params["mailto"] = self.email
        return params

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, str | int],
    ) -> dict[str, Any]:
        last_error: Exception | None = None

        for attempt in range(self.max_retries + 1):
            try:
                response = await self._client.get(path, params=params)
                if response.status_code == 429 or response.status_code >= 500:
                    if attempt >= self.max_retries:
                        response.raise_for_status()
                    await asyncio.sleep(_retry_delay_seconds(response, attempt))
                    continue

                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    raise OpenAlexProtocolError("OpenAlex response root must be an object")
                return payload
            except (httpx.HTTPError, ValueError, OpenAlexProtocolError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(min(2**attempt, 8))

        raise OpenAlexProtocolError("OpenAlex request failed after retries") from last_error

    def to_observation(
        self,
        work: dict[str, Any],
        *,
        query: OpenAlexQuery,
        observed_at: str | None = None,
    ) -> dict[str, Any]:
        work_id = _short_openalex_id(work.get("id"))
        if not work_id:
            raise OpenAlexProtocolError("OpenAlex work is missing a stable id")

        title = _as_nonempty_string(work.get("title") or work.get("display_name"))
        if not title:
            raise OpenAlexProtocolError(f"OpenAlex work {work_id} is missing a title")

        doi = _as_nonempty_string(work.get("doi"))
        canonical_url = doi or _as_nonempty_string(work.get("id"))

        authorships = work.get("authorships") if isinstance(work.get("authorships"), list) else []
        actors, actor_stats = _extract_actors(authorships)

        topics = work.get("topics") if isinstance(work.get("topics"), list) else []
        source_topics, classifications = _extract_topics(topics)

        open_access = work.get("open_access")
        if not isinstance(open_access, dict):
            open_access = {}

        primary_location = work.get("primary_location")
        if not isinstance(primary_location, dict):
            primary_location = {}
        best_oa_location = work.get("best_oa_location")
        if not isinstance(best_oa_location, dict):
            best_oa_location = {}

        referenced_works = work.get("referenced_works")
        if not isinstance(referenced_works, list):
            referenced_works = []
        locations = work.get("locations")
        if not isinstance(locations, list):
            locations = []

        published_at = (
            _as_nonempty_string(work.get("publication_date"))
            or _year_to_date(work.get("publication_year"))
        )
        updated_at = _as_nonempty_string(work.get("updated_date"))

        text = reconstruct_abstract(work.get("abstract_inverted_index"))

        metrics = {
            "cited_by_count": _primitive_or_none(work.get("cited_by_count")),
            "publication_year": _primitive_or_none(work.get("publication_year")),
            "work_type": _primitive_or_none(work.get("type")),
            "authorship_count": len(authorships),
            "institution_count": actor_stats["institution_total"],
            "locations_count": len(locations),
            "referenced_works_count": len(referenced_works),
            "fwci": _primitive_or_none(work.get("fwci")),
            "is_oa": _primitive_or_none(open_access.get("is_oa")),
            "oa_status": _primitive_or_none(open_access.get("oa_status")),
        }
        metrics = {k: v for k, v in metrics.items() if v is not None}

        quality_flags: dict[str, bool | str | int | float | None] = {
            "is_retracted": bool(work.get("is_retracted", False)),
            "is_paratext": bool(work.get("is_paratext", False)),
        }
        if actor_stats["truncated"]:
            quality_flags["actors_truncated"] = True

        license_value = (
            _as_nonempty_string(primary_location.get("license"))
            or _as_nonempty_string(best_oa_location.get("license"))
        )
        access_level = _as_nonempty_string(open_access.get("oa_status"))
        rights = None
        if license_value or access_level:
            rights = {
                "license": license_value,
                "access_level": access_level,
                "reuse_notes": None,
            }

        matched_terms = [query.effective_query_text]
        if query.effective_query_text.lower() != query.technology_direction.strip().lower():
            matched_terms.append(query.technology_direction.strip())

        observation: dict[str, Any] = {
            "schema_version": "0.2.0",
            "observation_id": f"openalex:{work_id}",
            "provider": "openalex",
            "evidence_type": "research",
            "artifact_kind": "paper",
            "external_id": work_id,
            "canonical_url": canonical_url,
            "title": title,
            "text": text,
            "published_at": published_at,
            "updated_at": updated_at,
            "observed_at": observed_at or _utc_now_iso(),
            "language": _as_nonempty_string(work.get("language")),
            "actors": actors,
            "source_topics": source_topics,
            "classifications": classifications,
            "metrics": metrics,
            "relationships": [],
            "quality_flags": quality_flags,
            "fingerprints": {
                "canonical_key": f"openalex:{work_id}",
                "content_hash": None,
                "simhash": None,
            },
            "collection_context": {
                "technology_direction": query.technology_direction.strip(),
                "source_profile": query.source_profile.strip(),
                "query_id": query.effective_query_id,
                "matched_terms": matched_terms,
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
                "collector": "openalex_rest",
                "collector_version": COLLECTOR_VERSION,
                "request_id": None,
                "source_endpoint": "GET /works",
            },
        }
        if rights is not None:
            observation["rights"] = rights

        return observation


def reconstruct_abstract(inverted_index: Any) -> str | None:
    """Rebuild the OpenAlex abstract from its inverted index representation."""
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None

    positions: list[tuple[int, str]] = []
    for token, raw_positions in inverted_index.items():
        if not isinstance(token, str) or not isinstance(raw_positions, list):
            continue
        for raw_position in raw_positions:
            if isinstance(raw_position, int) and raw_position >= 0:
                positions.append((raw_position, token))

    if not positions:
        return None

    positions.sort(key=lambda item: item[0])
    return " ".join(token for _position, token in positions)


def _extract_actors(
    authorships: list[Any],
    *,
    max_authors: int = 20,
    max_institutions: int = 20,
) -> tuple[list[dict[str, Any]], dict[str, int | bool]]:
    actors: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    author_total = 0
    institution_total = 0
    author_added = 0
    institution_added = 0

    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue

        author = authorship.get("author")
        if isinstance(author, dict):
            name = _as_nonempty_string(author.get("display_name"))
            external_id = _short_openalex_id(author.get("id"))
            if name:
                author_total += 1
                key = ("person", external_id or name.lower())
                if key not in seen and author_added < max_authors:
                    actors.append(
                        {
                            "name": name,
                            "kind": "person",
                            "external_id": external_id,
                            "country": None,
                        }
                    )
                    seen.add(key)
                    author_added += 1

        institutions = authorship.get("institutions")
        if not isinstance(institutions, list):
            continue
        for institution in institutions:
            if not isinstance(institution, dict):
                continue
            name = _as_nonempty_string(institution.get("display_name"))
            if not name:
                continue
            institution_total += 1
            external_id = _short_openalex_id(institution.get("id"))
            kind = _as_nonempty_string(institution.get("type")) or "institution"
            country = _as_nonempty_string(institution.get("country_code"))
            key = ("institution", external_id or name.lower())
            if key in seen or institution_added >= max_institutions:
                continue
            actors.append(
                {
                    "name": name,
                    "kind": kind,
                    "external_id": external_id,
                    "country": country,
                }
            )
            seen.add(key)
            institution_added += 1

    return actors, {
        "author_total": author_total,
        "institution_total": institution_total,
        "truncated": author_total > author_added or institution_total > institution_added,
    }


def _extract_topics(
    topics: list[Any],
    *,
    max_topics: int = 10,
) -> tuple[list[str], list[dict[str, Any]]]:
    source_topics: list[str] = []
    classifications: list[dict[str, Any]] = []

    for topic in topics[:max_topics]:
        if not isinstance(topic, dict):
            continue
        topic_id = _short_openalex_id(topic.get("id"))
        label = _as_nonempty_string(topic.get("display_name"))
        if label:
            source_topics.append(label)
        if topic_id:
            classifications.append(
                {
                    "scheme": "openalex_topic",
                    "value": topic_id,
                    "label": label,
                }
            )

    return source_topics, classifications


def _short_openalex_id(value: Any) -> str | None:
    text = _as_nonempty_string(value)
    if not text:
        return None
    return text.rstrip("/").rsplit("/", 1)[-1]


def _as_nonempty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _year_to_date(value: Any) -> str | None:
    if isinstance(value, int) and 1000 <= value <= 9999:
        return f"{value:04d}-01-01"
    return None


def _primitive_or_none(value: Any) -> str | int | float | bool | None:
    if isinstance(value, (str, int, float, bool)):
        return value
    return None


def _retry_delay_seconds(response: httpx.Response, attempt: int) -> float:
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return max(float(retry_after), 0.0)
        except ValueError:
            pass
    return min(2**attempt, 8)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
