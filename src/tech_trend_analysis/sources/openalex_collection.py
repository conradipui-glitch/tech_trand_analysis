from __future__ import annotations

from typing import Any

from tech_trend_analysis.collection import SourcePage
from tech_trend_analysis.sources.openalex import (
    OpenAlexAdapter,
    OpenAlexProtocolError,
    OpenAlexQuery,
)


class OpenAlexCollectionSource:
    """Page-oriented companion for OpenAlexAdapter.

    OpenAlexAdapter remains responsible for request construction, HTTP retries and
    Observation normalization. This companion only exposes provider pagination to
    the generic CollectionRunner.
    """

    provider = "openalex"

    def __init__(self, adapter: OpenAlexAdapter) -> None:
        self.adapter = adapter

    def checkpoint_key(self, query: OpenAlexQuery) -> str:
        return query.effective_query_id

    def initial_state(self, query: OpenAlexQuery) -> dict[str, Any]:
        return {"cursor": "*"}

    def page_limit(self, query: OpenAlexQuery) -> int:
        return query.max_pages

    async def fetch_page(
        self,
        query: OpenAlexQuery,
        *,
        state: dict[str, Any],
    ) -> SourcePage:
        cursor = state.get("cursor")
        if not isinstance(cursor, str) or not cursor:
            raise ValueError("OpenAlex continuation must contain non-empty cursor")

        params = self.adapter._build_params(query, cursor=cursor)
        payload = await self.adapter._get_json("/works", params=params)

        results = payload.get("results")
        meta = payload.get("meta")
        if not isinstance(results, list):
            raise OpenAlexProtocolError("OpenAlex response missing list 'results'")
        if not isinstance(meta, dict):
            raise OpenAlexProtocolError("OpenAlex response missing object 'meta'")

        raw_records = [record for record in results if isinstance(record, dict)]
        observed_at = _utc_now_iso()
        observations = [
            self.adapter.to_observation(
                record,
                query=query,
                observed_at=observed_at,
            )
            for record in raw_records
        ]

        next_cursor = meta.get("next_cursor")
        if not raw_records or not isinstance(next_cursor, str) or not next_cursor:
            next_state = None
        else:
            next_state = {"cursor": next_cursor}

        return SourcePage(
            raw_records=raw_records,
            observations=observations,
            next_state=next_state,
            observed_at=observed_at,
        )


def _utc_now_iso() -> str:
    from datetime import datetime, timezone

    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
