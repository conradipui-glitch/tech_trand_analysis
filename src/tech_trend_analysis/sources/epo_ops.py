"""Bounded EPO OPS v3.2 bibliographic patent collection.

Credentials are mandatory. Publication timestamps come only from EPO publication
references; neither priority dates nor the time of collection are backdated into
published_at. Search results remain unverified patent observations, not proof of
commercial adoption or independent technology relevance.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from tech_trend_analysis.collection import SourcePage

BASE_URL = "https://ops.epo.org/3.2/"
COLLECTOR_VERSION = "0.1.0"


class EPOOPSProtocolError(RuntimeError):
    """OPS data, authentication, or HTTP response cannot be trusted."""


class EPOOPSCredentialsMissing(EPOOPSProtocolError):
    """Live OPS access requires an EPO developer application key and secret."""


@dataclass(frozen=True, slots=True)
class EPOOPSQuery:
    technology_direction: str
    source_profile: str
    cql: str
    query_id: str | None = None
    per_page: int = 25
    max_pages: int = 2

    def __post_init__(self) -> None:
        if not self.technology_direction.strip() or not self.source_profile.strip():
            raise ValueError("technology_direction and source_profile are required")
        if not self.cql.strip() or len(self.cql) > 500 or any(x in self.cql for x in "\r\n"):
            raise ValueError("cql must be 1..500 characters without newlines")
        if not 1 <= self.per_page <= 25:
            raise ValueError("per_page must be 1..25 for bounded OPS collection")
        if not 1 <= self.max_pages <= 20:
            raise ValueError("max_pages must be 1..20")

    @property
    def effective_query_id(self) -> str:
        if self.query_id:
            return self.query_id
        key = "|".join((
            self.technology_direction.strip().casefold(),
            self.source_profile, self.cql, str(self.per_page),
        ))
        return "epo_ops:" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


class EPOOPSAdapter:
    """OAuth client_credentials and normalization of bibliographic OPS XML.

    Implements PaginatedSource for CollectionRunner's raw-before-checkpoint
    storage. Search match alone never passes downstream semantic relevance.
    """
    provider = "epo_ops"

    def __init__(
        self,
        *,
        consumer_key: str | None = None,
        consumer_secret: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 20.0,
    ) -> None:
        if not consumer_key or not consumer_key.strip() or not consumer_secret or not consumer_secret.strip():
            raise EPOOPSCredentialsMissing("EPO OPS consumer key and secret are required")
        self._key = consumer_key.strip()
        self._secret = consumer_secret.strip()
        self._external_client = client is not None
        self._client = client or httpx.AsyncClient(base_url=BASE_URL, timeout=timeout)
        self._token: str | None = None
        self._token_expires_at = 0.0

    @classmethod
    def from_environment(cls, **kwargs: Any) -> "EPOOPSAdapter":
        return cls(
            consumer_key=os.environ.get("EPO_OPS_CONSUMER_KEY"),
            consumer_secret=os.environ.get("EPO_OPS_CONSUMER_SECRET"),
            **kwargs,
        )

    async def __aenter__(self) -> "EPOOPSAdapter":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if not self._external_client:
            await self._client.aclose()

    def checkpoint_key(self, query: EPOOPSQuery) -> str:
        return query.effective_query_id

    def initial_state(self, query: EPOOPSQuery) -> dict[str, Any]:
        return {"start": 1}

    def page_limit(self, query: EPOOPSQuery) -> int:
        return query.max_pages

    async def fetch_page(self, query: EPOOPSQuery, *, state: dict[str, Any]) -> SourcePage:
        start = state.get("start")
        if isinstance(start, bool) or not isinstance(start, int) or start < 1 or (start - 1) % query.per_page:
            raise ValueError("invalid OPS search continuation")
        end = start + query.per_page - 1
        token = await self._access_token()
        try:
            response = await self._client.get(
                "rest-services/published-data/search/biblio",
                params={"q": query.cql},
                headers={
                    "Accept": "application/ops+xml",
                    "Authorization": f"Bearer {token}",
                    "X-OPS-Range": f"{start}-{end}",
                },
            )
        except httpx.HTTPError as exc:
            raise EPOOPSProtocolError("OPS search request failed") from exc
        if response.status_code == 401:
            self._token = None
            self._token_expires_at = 0
            raise EPOOPSProtocolError("OPS authorization rejected; check credentials")
        if response.status_code == 429:
            raise EPOOPSProtocolError("OPS rate limit reached; retry later")
        if response.status_code >= 400:
            raise EPOOPSProtocolError(f"OPS search HTTP {response.status_code}")

        root = _safe_parse_xml(response.content)
        items = root.findall(".//{*}exchange-document")
        if not items and root.tag.rsplit("}", 1)[-1] != "world-patent-data":
            raise EPOOPSProtocolError("OPS search response is not world-patent-data")
        observed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        observations: list[dict[str, Any]] = []
        raw_records: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in items:
            record = self.to_observation(item, query=query, observed_at=observed_at)
            if record["external_id"] in seen:
                continue
            seen.add(record["external_id"])
            observations.append(record)
            raw_records.append({"xml": ET.tostring(item, encoding="unicode")})

        # A full page may have another page even when dedup has fewer records.
        next_state = {"start": end + 1} if len(items) == query.per_page else None
        return SourcePage(
            raw_records=raw_records,
            observations=observations,
            next_state=next_state,
            observed_at=observed_at,
        )

    async def _access_token(self) -> str:
        if self._token and time.monotonic() < self._token_expires_at:
            return self._token
        try:
            response = await self._client.post(
                "auth/accesstoken",
                auth=(self._key, self._secret),
                data={"grant_type": "client_credentials"},
                headers={"Accept": "application/json"},
            )
        except httpx.HTTPError as exc:
            raise EPOOPSProtocolError("OPS OAuth token request failed") from exc
        if response.status_code != 200:
            raise EPOOPSProtocolError(f"OPS OAuth HTTP {response.status_code}")
        try:
            payload = response.json()
            token = payload["access_token"]
            expires_in = int(payload["expires_in"])
            if not isinstance(token, str) or not token or expires_in <= 0:
                raise ValueError("bad token payload")
        except (ValueError, KeyError, TypeError) as exc:
            raise EPOOPSProtocolError("OPS OAuth response lacks valid access token") from exc
        self._token = token
        self._token_expires_at = time.monotonic() + max(0, expires_in - 60)
        return token

    def to_observation(
        self, item: ET.Element, *, query: EPOOPSQuery, observed_at: str
    ) -> dict[str, Any]:
        biblio = item.find("{*}bibliographic-data")
        if biblio is None:
            raise EPOOPSProtocolError("OPS exchange-document missing bibliographic-data")
        ref = biblio.find("{*}publication-reference")
        if ref is None:
            raise EPOOPSProtocolError("OPS document missing publication-reference")
        ids = ref.findall("{*}document-id")
        preferred = next((x for x in ids if x.get("document-id-type") == "docdb"), None)
        document_id = preferred if preferred is not None else (ids[0] if ids else None)
        if document_id is None:
            raise EPOOPSProtocolError("OPS publication missing document-id")
        country = _text(document_id, "{*}country")
        number = _text(document_id, "{*}doc-number")
        kind = _text(document_id, "{*}kind")
        if not country or not number or not kind or not re.fullmatch(r"[A-Za-z0-9]+", country + number + kind):
            raise EPOOPSProtocolError("OPS publication lacks a stable DOCDB identity")
        external_id = f"{country.upper()}{number}{kind.upper()}"
        titles = biblio.findall("{*}invention-title")
        en_title = next(
            (x for x in titles if (x.get("lang") or "").lower() == "en" and "".join(x.itertext()).strip()),
            None,
        )
        chosen_title = en_title if en_title is not None else (titles[0] if titles else None)
        title = " ".join("".join(chosen_title.itertext()).split()) if chosen_title is not None else ""
        if not title:
            raise EPOOPSProtocolError("OPS patent lacks a bibliographic title")
        raw_date = _text(document_id, "{*}date")
        published_at = None
        if raw_date:
            if not re.fullmatch(r"\d{8}", raw_date):
                raise EPOOPSProtocolError("OPS publication date format not recognized")
            try:
                published_at = datetime.strptime(raw_date, "%Y%m%d").date().isoformat()
            except ValueError as exc:
                raise EPOOPSProtocolError("OPS publication date invalid") from exc

        applicants: list[dict[str, Any]] = []
        seen_actors: set[str] = set()
        for applicant in biblio.findall(".//{*}applicants/{*}applicant"):
            name_node = applicant.find(".//{*}applicant-name/{*}name")
            if name_node is None:
                name_node = applicant.find(".//{*}name")
            name = " ".join("".join(name_node.itertext()).split()) if name_node is not None else ""
            if not name or name.casefold() in seen_actors:
                continue
            seen_actors.add(name.casefold())
            country_node = applicant.find(".//{*}addressbook/{*}address/{*}country")
            applicants.append({
                "name": name, "kind": "organization", "external_id": None,
                "country": ((country_node.text or "").strip() or None) if country_node is not None else None,
            })

        classifications: list[dict[str, str]] = []
        codes: set[tuple[str, str]] = set()
        for scheme, tag in (("IPC", "classification-ipcr"), ("CPC", "classification-cpc")):
            for el in biblio.findall(f".//{{*}}{tag}"):
                text_code = " ".join("".join(el.itertext()).split())
                if text_code and (scheme, text_code) not in codes:
                    codes.add((scheme, text_code))
                    classifications.append({"scheme": scheme, "value": text_code})

        abstracts = item.findall("{*}abstract")
        abstract_en = next((a for a in abstracts if (a.get("lang") or "").lower() == "en"), None)
        abstract = abstract_en if abstract_en is not None else (abstracts[0] if abstracts else None)
        compact_text = " ".join(" ".join(abstract.itertext()).split()) if abstract is not None else None
        family_id = item.get("family-id")
        return {
            "schema_version": "0.2.0", "observation_id": f"epo_ops:{external_id}",
            "provider": "epo_ops", "evidence_type": "patent", "artifact_kind": "patent",
            "external_id": external_id, "canonical_url": None, "title": title,
            "text": compact_text, "published_at": published_at, "updated_at": None,
            "observed_at": observed_at, "language": chosen_title.get("lang") if chosen_title is not None else None,
            "actors": applicants, "source_topics": [], "classifications": classifications,
            "metrics": {},
            "relationships": (
                [{"type": "patent_family", "target_id": f"epo_ops:family:{family_id}"}]
                if family_id and family_id.strip() else []
            ),
            "quality_flags": {"publication_date_missing": published_at is None, "patent_is_not_adoption_proof": True},
            "fingerprints": {"canonical_key": f"epo_ops:{external_id}", "content_hash": None, "simhash": None},
            "collection_context": {
                "technology_direction": query.technology_direction.strip(),
                "source_profile": query.source_profile.strip(),
                "query_id": query.effective_query_id,
                "matched_terms": [],
            },
            "analysis": {
                "relevance": None, "novelty": None, "cluster_id": None,
                "embedding_ref": None, "technology_labels": [],
            },
            "raw_ref": None,
            "provenance": {
                "collector": "epo_ops", "collector_version": COLLECTOR_VERSION,
                "request_id": None, "source_endpoint": "GET /published-data/search/biblio",
            },
        }


def _text(parent: ET.Element, tag: str) -> str | None:
    value = parent.find(tag)
    return ((value.text or "").strip() or None) if value is not None else None


def _safe_parse_xml(payload: bytes) -> ET.Element:
    if len(payload) > 3_000_000 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise EPOOPSProtocolError("OPS XML unsafe or too large")
    try:
        return ET.fromstring(payload)
    except ET.ParseError as exc:
        raise EPOOPSProtocolError("OPS XML malformed") from exc
