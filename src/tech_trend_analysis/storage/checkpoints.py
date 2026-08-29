from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


CHECKPOINT_VERSION = "0.1.0"
_PROVIDER_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class CheckpointRecord:
    provider: str
    key: str
    state: dict[str, Any]
    updated_at: str
    version: str = CHECKPOINT_VERSION


class CheckpointStore(Protocol):
    async def load(self, provider: str, key: str) -> CheckpointRecord | None: ...

    async def save(
        self,
        provider: str,
        key: str,
        state: dict[str, Any],
        *,
        updated_at: str | None = None,
    ) -> CheckpointRecord: ...

    async def delete(self, provider: str, key: str) -> None: ...


class MemoryCheckpointStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], CheckpointRecord] = {}

    async def load(self, provider: str, key: str) -> CheckpointRecord | None:
        _validate_identity(provider, key)
        return self._records.get((provider, key))

    async def save(
        self,
        provider: str,
        key: str,
        state: dict[str, Any],
        *,
        updated_at: str | None = None,
    ) -> CheckpointRecord:
        _validate_identity(provider, key)
        _validate_state(state)
        record = CheckpointRecord(
            provider=provider,
            key=key,
            state=dict(state),
            updated_at=updated_at or _utc_now_iso(),
        )
        self._records[(provider, key)] = record
        return record

    async def delete(self, provider: str, key: str) -> None:
        _validate_identity(provider, key)
        self._records.pop((provider, key), None)


class FileCheckpointStore:
    """Atomic JSON checkpoint store for local/VPS development."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    async def load(self, provider: str, key: str) -> CheckpointRecord | None:
        _validate_identity(provider, key)
        return await asyncio.to_thread(self._load_sync, provider, key)

    async def save(
        self,
        provider: str,
        key: str,
        state: dict[str, Any],
        *,
        updated_at: str | None = None,
    ) -> CheckpointRecord:
        _validate_identity(provider, key)
        _validate_state(state)
        record = CheckpointRecord(
            provider=provider,
            key=key,
            state=dict(state),
            updated_at=updated_at or _utc_now_iso(),
        )
        await asyncio.to_thread(self._save_sync, record)
        return record

    async def delete(self, provider: str, key: str) -> None:
        _validate_identity(provider, key)
        await asyncio.to_thread(self._delete_sync, provider, key)

    def _path_for(self, provider: str, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.root / provider / f"{digest}.json"

    def _load_sync(self, provider: str, key: str) -> CheckpointRecord | None:
        path = self._path_for(provider, key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"checkpoint root must be object: {path}")
        record = CheckpointRecord(
            provider=str(payload["provider"]),
            key=str(payload["key"]),
            state=dict(payload["state"]),
            updated_at=str(payload["updated_at"]),
            version=str(payload.get("version") or CHECKPOINT_VERSION),
        )
        if record.provider != provider or record.key != key:
            raise ValueError(f"checkpoint identity mismatch: {path}")
        return record

    def _save_sync(self, record: CheckpointRecord) -> None:
        path = self._path_for(record.provider, record.key)
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            asdict(record),
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ) + "\n"

        fd, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.",
            suffix=".tmp",
            dir=path.parent,
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
        except Exception:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise

    def _delete_sync(self, provider: str, key: str) -> None:
        path = self._path_for(provider, key)
        try:
            path.unlink()
        except FileNotFoundError:
            return


def _validate_identity(provider: str, key: str) -> None:
    if not provider or not _PROVIDER_RE.fullmatch(provider):
        raise ValueError("provider must match [A-Za-z0-9_.-]+")
    if not isinstance(key, str) or not key.strip():
        raise ValueError("checkpoint key must be a non-empty string")


def _validate_state(state: dict[str, Any]) -> None:
    if not isinstance(state, dict):
        raise TypeError("checkpoint state must be a dict")
    try:
        json.dumps(state)
    except (TypeError, ValueError) as exc:
        raise TypeError("checkpoint state must be JSON-serializable") from exc


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
