from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Generic, Protocol, TypeVar

from tech_trend_analysis.storage.checkpoints import CheckpointStore
from tech_trend_analysis.storage.raw import RawBatchRef, RawSink


QueryT = TypeVar("QueryT")


@dataclass(frozen=True, slots=True)
class SourcePage:
    """One provider page before and after normalization."""

    raw_records: list[dict[str, Any]]
    observations: list[dict[str, Any]]
    next_state: dict[str, Any] | None
    observed_at: str


class PaginatedSource(Protocol, Generic[QueryT]):
    provider: str

    def checkpoint_key(self, query: QueryT) -> str: ...

    def initial_state(self, query: QueryT) -> dict[str, Any]: ...

    def page_limit(self, query: QueryT) -> int: ...

    async def fetch_page(
        self,
        query: QueryT,
        *,
        state: dict[str, Any],
    ) -> SourcePage: ...


@dataclass(frozen=True, slots=True)
class CollectionRunResult:
    provider: str
    checkpoint_key: str
    resumed: bool
    complete: bool
    pages_collected: int
    observations_collected: int
    observations: list[dict[str, Any]]
    raw_batches: list[RawBatchRef]


class CollectionRunner:
    """Run a provider incrementally with raw-before-checkpoint durability.

    Commit order for every page:

    1. fetch provider page;
    2. persist the raw page;
    3. attach the durable raw reference to normalized observations;
    4. save continuation checkpoint.

    If a later page fails, the next run resumes from the last committed page.
    If a crash happens after raw write but before checkpoint save, the same page may
    be fetched again. The deterministic batch id makes local/R2 raw storage
    idempotent, while downstream dedup remains the final safety net.
    """

    def __init__(
        self,
        *,
        checkpoints: CheckpointStore,
        raw_sink: RawSink,
    ) -> None:
        self.checkpoints = checkpoints
        self.raw_sink = raw_sink

    async def run(
        self,
        source: PaginatedSource[QueryT],
        query: QueryT,
        *,
        max_pages: int | None = None,
    ) -> CollectionRunResult:
        provider = source.provider
        checkpoint_key = source.checkpoint_key(query)
        checkpoint = await self.checkpoints.load(provider, checkpoint_key)
        resumed = checkpoint is not None

        if checkpoint and bool(checkpoint.state.get("complete")):
            return CollectionRunResult(
                provider=provider,
                checkpoint_key=checkpoint_key,
                resumed=True,
                complete=True,
                pages_collected=0,
                observations_collected=0,
                observations=[],
                raw_batches=[],
            )

        if checkpoint:
            continuation = checkpoint.state.get("continuation")
            if not isinstance(continuation, dict):
                raise ValueError("incomplete checkpoint must contain object continuation")
            state = dict(continuation)
            total_pages_before = _nonnegative_int(checkpoint.state.get("pages_completed"))
            total_observations_before = _nonnegative_int(
                checkpoint.state.get("observations_completed")
            )
        else:
            state = dict(source.initial_state(query))
            total_pages_before = 0
            total_observations_before = 0

        page_budget = max_pages if max_pages is not None else source.page_limit(query)
        if page_budget < 1:
            raise ValueError("max_pages/page_limit must be >= 1")

        collected: list[dict[str, Any]] = []
        raw_batches: list[RawBatchRef] = []
        complete = False

        for page_index in range(page_budget):
            page = await source.fetch_page(query, state=state)
            if not isinstance(page, SourcePage):
                raise TypeError("fetch_page must return SourcePage")

            raw_ref: RawBatchRef | None = None
            if page.raw_records:
                raw_ref = await self.raw_sink.write_batch(
                    provider,
                    page.raw_records,
                    observed_at=page.observed_at,
                    batch_id=_deterministic_batch_id(
                        provider=provider,
                        checkpoint_key=checkpoint_key,
                        state=state,
                    ),
                )
                raw_batches.append(raw_ref)

            page_observations = [
                _attach_raw_ref(observation, raw_ref)
                for observation in page.observations
            ]
            collected.extend(page_observations)

            complete = page.next_state is None
            pages_completed = total_pages_before + page_index + 1
            observations_completed = total_observations_before + len(collected)
            checkpoint_state: dict[str, Any] = {
                "complete": complete,
                "continuation": None if complete else dict(page.next_state),
                "pages_completed": pages_completed,
                "observations_completed": observations_completed,
                "last_raw_ref": raw_ref.uri if raw_ref else None,
            }
            await self.checkpoints.save(provider, checkpoint_key, checkpoint_state)

            if complete:
                break
            state = dict(page.next_state)

        return CollectionRunResult(
            provider=provider,
            checkpoint_key=checkpoint_key,
            resumed=resumed,
            complete=complete,
            pages_collected=page_index + 1,
            observations_collected=len(collected),
            observations=collected,
            raw_batches=raw_batches,
        )


def _attach_raw_ref(
    observation: dict[str, Any],
    raw_ref: RawBatchRef | None,
) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise TypeError("observations must be dict objects")
    normalized = dict(observation)
    if raw_ref is not None:
        normalized["raw_ref"] = raw_ref.uri
    return normalized


def _deterministic_batch_id(
    *,
    provider: str,
    checkpoint_key: str,
    state: dict[str, Any],
) -> str:
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(
        f"{provider}|{checkpoint_key}|{payload}".encode("utf-8")
    ).hexdigest()[:24]
    return f"page-{digest}"


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int) and value >= 0:
        return value
    return 0
