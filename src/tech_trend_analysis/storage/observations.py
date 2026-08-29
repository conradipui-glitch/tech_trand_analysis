from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Protocol


@dataclass(frozen=True, slots=True)
class UpsertStats:
    inserted: int
    updated: int


class ObservationStore(Protocol):
    async def upsert_many(self, observations: Iterable[dict[str, Any]]) -> UpsertStats: ...

    async def get(self, observation_id: str) -> dict[str, Any] | None: ...

    async def list_observations(
        self,
        *,
        technology_direction: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]: ...


class MemoryObservationStore:
    def __init__(self) -> None:
        self._items: dict[str, dict[str, Any]] = {}

    async def upsert_many(self, observations: Iterable[dict[str, Any]]) -> UpsertStats:
        inserted = 0
        updated = 0
        for observation in observations:
            payload = _validated_copy(observation)
            observation_id = payload["observation_id"]
            if observation_id in self._items:
                updated += 1
            else:
                inserted += 1
            self._items[observation_id] = payload
        return UpsertStats(inserted=inserted, updated=updated)

    async def get(self, observation_id: str) -> dict[str, Any] | None:
        value = self._items.get(_validate_id(observation_id))
        return dict(value) if value is not None else None

    async def list_observations(
        self,
        *,
        technology_direction: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        _validate_limit(limit)
        values = list(self._items.values())
        if technology_direction is not None:
            values = [
                item
                for item in values
                if _technology_direction(item) == technology_direction
            ]
        return [dict(item) for item in values[:limit]]


class SqliteObservationStore:
    """SQLite normalized store with a schema intentionally easy to port to D1."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def upsert_many(self, observations: Iterable[dict[str, Any]]) -> UpsertStats:
        materialized = [_validated_copy(item) for item in observations]
        if not materialized:
            return UpsertStats(inserted=0, updated=0)
        return await asyncio.to_thread(self._upsert_many_sync, materialized)

    async def get(self, observation_id: str) -> dict[str, Any] | None:
        observation_id = _validate_id(observation_id)
        return await asyncio.to_thread(self._get_sync, observation_id)

    async def list_observations(
        self,
        *,
        technology_direction: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        _validate_limit(limit)
        return await asyncio.to_thread(
            self._list_sync,
            technology_direction,
            limit,
        )

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        self._ensure_schema(connection)
        return connection

    def _ensure_schema(self, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                evidence_type TEXT NOT NULL,
                artifact_kind TEXT NOT NULL,
                canonical_url TEXT,
                published_at TEXT,
                observed_at TEXT NOT NULL,
                technology_direction TEXT,
                cluster_id TEXT,
                payload_json TEXT NOT NULL,
                stored_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_observations_direction
                ON observations(technology_direction);
            CREATE INDEX IF NOT EXISTS idx_observations_evidence
                ON observations(evidence_type, artifact_kind);
            CREATE INDEX IF NOT EXISTS idx_observations_published
                ON observations(published_at);
            """
        )

    def _upsert_many_sync(self, observations: list[dict[str, Any]]) -> UpsertStats:
        inserted = 0
        updated = 0
        with self._connect() as connection:
            for observation in observations:
                observation_id = observation["observation_id"]
                exists = connection.execute(
                    "SELECT 1 FROM observations WHERE observation_id = ?",
                    (observation_id,),
                ).fetchone()
                if exists:
                    updated += 1
                else:
                    inserted += 1

                connection.execute(
                    """
                    INSERT INTO observations (
                        observation_id,
                        provider,
                        evidence_type,
                        artifact_kind,
                        canonical_url,
                        published_at,
                        observed_at,
                        technology_direction,
                        cluster_id,
                        payload_json,
                        stored_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(observation_id) DO UPDATE SET
                        provider = excluded.provider,
                        evidence_type = excluded.evidence_type,
                        artifact_kind = excluded.artifact_kind,
                        canonical_url = excluded.canonical_url,
                        published_at = excluded.published_at,
                        observed_at = excluded.observed_at,
                        technology_direction = excluded.technology_direction,
                        cluster_id = excluded.cluster_id,
                        payload_json = excluded.payload_json,
                        stored_at = CURRENT_TIMESTAMP
                    """,
                    _row_values(observation),
                )
        return UpsertStats(inserted=inserted, updated=updated)

    def _get_sync(self, observation_id: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT payload_json FROM observations WHERE observation_id = ?",
                (observation_id,),
            ).fetchone()
        if row is None:
            return None
        return json.loads(row["payload_json"])

    def _list_sync(
        self,
        technology_direction: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        with self._connect() as connection:
            if technology_direction is None:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM observations
                    ORDER BY observed_at, observation_id
                    LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM observations
                    WHERE technology_direction = ?
                    ORDER BY observed_at, observation_id
                    LIMIT ?
                    """,
                    (technology_direction, limit),
                ).fetchall()
        return [json.loads(row["payload_json"]) for row in rows]


def _row_values(observation: dict[str, Any]) -> tuple[Any, ...]:
    analysis = observation.get("analysis")
    cluster_id = analysis.get("cluster_id") if isinstance(analysis, dict) else None
    return (
        observation["observation_id"],
        observation["provider"],
        observation["evidence_type"],
        observation["artifact_kind"],
        observation.get("canonical_url"),
        observation.get("published_at"),
        observation["observed_at"],
        _technology_direction(observation),
        cluster_id,
        json.dumps(observation, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )


def _technology_direction(observation: dict[str, Any]) -> str | None:
    context = observation.get("collection_context")
    if not isinstance(context, dict):
        return None
    value = context.get("technology_direction")
    return value if isinstance(value, str) else None


def _validated_copy(observation: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise TypeError("observation must be a dict")
    required = (
        "observation_id",
        "provider",
        "evidence_type",
        "artifact_kind",
        "observed_at",
    )
    for key in required:
        value = observation.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{key} must be a non-empty string")
    try:
        json.dumps(observation)
    except (TypeError, ValueError) as exc:
        raise TypeError("observation must be JSON-serializable") from exc
    return json.loads(json.dumps(observation, ensure_ascii=False))


def _validate_id(observation_id: str) -> str:
    if not isinstance(observation_id, str) or not observation_id.strip():
        raise ValueError("observation_id must be a non-empty string")
    return observation_id.strip()


def _validate_limit(limit: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer")
