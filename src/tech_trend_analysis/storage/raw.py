from __future__ import annotations

import asyncio
import gzip
import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Protocol


_PROVIDER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class RawBatchRef:
    provider: str
    batch_id: str
    uri: str
    record_count: int
    created_at: str
    sha256: str
    content_type: str = "application/x-ndjson+gzip"


class RawSink(Protocol):
    async def write_batch(
        self,
        provider: str,
        records: Iterable[dict[str, Any]],
        *,
        observed_at: str | None = None,
        batch_id: str | None = None,
    ) -> RawBatchRef: ...


class JsonlGzipRawSink:
    """Append-oriented local raw buffer mirroring the future R2 key layout."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    async def write_batch(
        self,
        provider: str,
        records: Iterable[dict[str, Any]],
        *,
        observed_at: str | None = None,
        batch_id: str | None = None,
    ) -> RawBatchRef:
        _validate_provider(provider)
        materialized = list(records)
        if not materialized:
            raise ValueError("raw batch must contain at least one record")
        for record in materialized:
            if not isinstance(record, dict):
                raise TypeError("raw records must be dict objects")

        created = _parse_or_now(observed_at)
        resolved_batch_id = batch_id or uuid.uuid4().hex
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", resolved_batch_id):
            raise ValueError("batch_id must match [A-Za-z0-9_.-]+")

        return await asyncio.to_thread(
            self._write_sync,
            provider,
            materialized,
            created,
            resolved_batch_id,
        )

    def _write_sync(
        self,
        provider: str,
        records: list[dict[str, Any]],
        created: datetime,
        batch_id: str,
    ) -> RawBatchRef:
        relative = Path(
            "raw",
            provider,
            f"{created.year:04d}",
            f"{created.month:02d}",
            f"{created.day:02d}",
            f"{batch_id}.jsonl.gz",
        )
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)

        hasher = hashlib.sha256()
        with path.open("wb") as raw_handle:
            with gzip.GzipFile(fileobj=raw_handle, mode="wb", mtime=0) as zipped:
                for record in records:
                    line = (
                        json.dumps(
                            record,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                        + "\n"
                    ).encode("utf-8")
                    zipped.write(line)

        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                hasher.update(chunk)

        return RawBatchRef(
            provider=provider,
            batch_id=batch_id,
            uri=path.resolve().as_uri(),
            record_count=len(records),
            created_at=created.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            sha256=hasher.hexdigest(),
        )


def _validate_provider(provider: str) -> None:
    if not provider or not _PROVIDER_RE.fullmatch(provider):
        raise ValueError("provider must match [A-Za-z0-9_.-]+")


def _parse_or_now(value: str | None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    normalized = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include timezone")
    return parsed.astimezone(timezone.utc)
