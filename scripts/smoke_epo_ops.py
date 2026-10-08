"""One-shot authenticated EPO OPS smoke. Explicit opt-in; no secrets printed."""
from __future__ import annotations

import asyncio
import json

from tech_trend_analysis.sources.epo_ops import EPOOPSAdapter, EPOOPSQuery


async def main() -> None:
    query = EPOOPSQuery(
        technology_direction="solid-state batteries",
        source_profile="materials_energy",
        cql='ti="solid state battery"',
        per_page=5,
        max_pages=1,
    )
    async with EPOOPSAdapter.from_environment() as adapter:
        page = await adapter.fetch_page(query, state=adapter.initial_state(query))
    print(json.dumps({
        "provider": "epo_ops",
        "transport": "authenticated",
        "observations": len(page.observations),
        "dated_publications": sum(o["published_at"] is not None for o in page.observations),
        "next_page_available": page.next_state is not None,
        "relevance_verified": False,
    }, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
