import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

import httpx
from jsonschema import Draft202012Validator, FormatChecker

from tech_trend_analysis.collection import CollectionRunner
from tech_trend_analysis.sources.openalex import OpenAlexAdapter, OpenAlexQuery
from tech_trend_analysis.sources.openalex_collection import OpenAlexCollectionSource
from tech_trend_analysis.storage.checkpoints import MemoryCheckpointStore
from tech_trend_analysis.storage.raw import JsonlGzipRawSink


ROOT = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class OpenAlexCollectionVerticalSliceTests(unittest.IsolatedAsyncioTestCase):
    async def test_openalex_page_becomes_durable_valid_observation(self):
        work = load_json(ROOT / "tests" / "fixtures" / "openalex_work.json")
        schema = load_json(ROOT / "schemas" / "observation.schema.json")
        validator = Draft202012Validator(schema, format_checker=FormatChecker())

        def handler(request: httpx.Request):
            self.assertEqual("*", request.url.params["cursor"])
            return httpx.Response(
                200,
                json={"results": [work], "meta": {"next_cursor": None}},
            )

        query = OpenAlexQuery(
            technology_direction="neuromorphic computing",
            source_profile="hardware_semiconductor",
            query_text="neuromorphic computing",
            from_date=date(2026, 8, 1),
            to_date=date(2026, 8, 29),
            max_pages=3,
        )

        checkpoints = MemoryCheckpointStore()
        with tempfile.TemporaryDirectory() as tempdir:
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(handler),
                base_url="https://api.openalex.org",
            ) as client:
                adapter = OpenAlexAdapter(client=client)
                source = OpenAlexCollectionSource(adapter)
                runner = CollectionRunner(
                    checkpoints=checkpoints,
                    raw_sink=JsonlGzipRawSink(tempdir),
                )
                result = await runner.run(source, query)

            self.assertTrue(result.complete)
            self.assertEqual(1, result.pages_collected)
            self.assertEqual(1, result.observations_collected)
            self.assertEqual(1, len(result.raw_batches))

            observation = result.observations[0]
            errors = sorted(
                validator.iter_errors(observation),
                key=lambda error: list(error.path),
            )
            self.assertEqual([], [error.message for error in errors])
            self.assertEqual("openalex:W123456789", observation["observation_id"])
            self.assertEqual(result.raw_batches[0].uri, observation["raw_ref"])
            self.assertTrue(Path(result.raw_batches[0].uri.removeprefix("file://")).exists())

            checkpoint = await checkpoints.load("openalex", query.effective_query_id)
            self.assertIsNotNone(checkpoint)
            self.assertTrue(checkpoint.state["complete"])
            self.assertEqual(1, checkpoint.state["pages_completed"])
            self.assertEqual(1, checkpoint.state["observations_completed"])


if __name__ == "__main__":
    unittest.main()
