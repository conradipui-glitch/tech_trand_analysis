import json
import unittest
from datetime import date
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from tech_trend_analysis.sources.openalex import (
    OpenAlexAdapter,
    OpenAlexQuery,
    reconstruct_abstract,
)

ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class OpenAlexAdapterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.work = load_json(ROOT / "tests" / "fixtures" / "openalex_work.json")
        schema = load_json(ROOT / "schemas" / "observation.schema.json")
        self.validator = Draft202012Validator(schema, format_checker=FormatChecker())
        self.query = OpenAlexQuery(
            technology_direction="neuromorphic computing",
            source_profile="hardware_semiconductor",
            query_text="neuromorphic edge intelligence",
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 29),
            per_page=100,
            max_pages=3,
        )

    def assert_valid(self, payload):
        errors = sorted(self.validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors])

    async def test_mapping_validates_against_observation_contract(self):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, json={})),
            base_url="https://api.openalex.org",
        ) as client:
            adapter = OpenAlexAdapter(client=client)
            observation = adapter.to_observation(
                self.work,
                query=self.query,
                observed_at="2026-08-29T16:45:00Z",
            )

        self.assert_valid(observation)
        self.assertEqual("openalex:W123456789", observation["observation_id"])
        self.assertEqual("research", observation["evidence_type"])
        self.assertEqual("Neuromorphic edge systems reduce energy use.", observation["text"])
        self.assertEqual(7, observation["metrics"]["cited_by_count"])
        self.assertEqual("Neuromorphic Computing", observation["source_topics"][0])
        self.assertEqual("A1", observation["actors"][0]["external_id"])
        self.assertEqual("I1", observation["actors"][1]["external_id"])

    def test_reconstruct_abstract(self):
        self.assertEqual(
            "Neuromorphic edge systems reduce energy use.",
            reconstruct_abstract(self.work["abstract_inverted_index"]),
        )
        self.assertIsNone(reconstruct_abstract(None))

    async def test_cursor_pagination_and_query_params(self):
        requests = []
        second_work = dict(self.work)
        second_work["id"] = "https://openalex.org/W987654321"
        second_work["doi"] = None
        second_work["title"] = "Second Work"

        def handler(request: httpx.Request):
            requests.append(request)
            cursor = request.url.params.get("cursor")
            if cursor == "*":
                return httpx.Response(
                    200,
                    json={"results": [self.work], "meta": {"next_cursor": "NEXT"}},
                )
            if cursor == "NEXT":
                return httpx.Response(
                    200,
                    json={"results": [second_work], "meta": {"next_cursor": None}},
                )
            return httpx.Response(400, json={"error": "unexpected cursor"})

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler),
            base_url="https://api.openalex.org",
        ) as client:
            adapter = OpenAlexAdapter(
                client=client,
                api_key="test-key",
                email="test@example.com",
            )
            observations = await adapter.collect_recent(self.query)

        self.assertEqual(2, len(observations))
        self.assertEqual(["*", "NEXT"], [request.url.params["cursor"] for request in requests])
        first = requests[0].url.params
        self.assertEqual("neuromorphic edge intelligence", first["search"])
        self.assertIn("from_publication_date:2026-08-01", first["filter"])
        self.assertIn("to_publication_date:2026-08-29", first["filter"])
        self.assertEqual("100", first["per-page"])
        self.assertEqual("test-key", first["api_key"])
        self.assertEqual("test@example.com", first["mailto"])

    def test_query_id_is_deterministic(self):
        self.assertEqual(self.query.effective_query_id, self.query.effective_query_id)
        self.assertTrue(self.query.effective_query_id.startswith("openalex:"))


if __name__ == "__main__":
    unittest.main()
