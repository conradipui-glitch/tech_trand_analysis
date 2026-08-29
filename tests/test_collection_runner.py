import tempfile
import unittest
from pathlib import Path

from tech_trend_analysis.collection import CollectionRunner, SourcePage
from tech_trend_analysis.storage.checkpoints import MemoryCheckpointStore
from tech_trend_analysis.storage.raw import JsonlGzipRawSink


class FakeSource:
    provider = "fake"

    def __init__(self, *, fail_on_b: bool = False) -> None:
        self.fail_on_b = fail_on_b
        self.calls: list[str] = []

    def checkpoint_key(self, query: str) -> str:
        return f"fake:{query}"

    def initial_state(self, query: str):
        return {"cursor": "A"}

    def page_limit(self, query: str) -> int:
        return 10

    async def fetch_page(self, query: str, *, state):
        cursor = state["cursor"]
        self.calls.append(cursor)
        if cursor == "A":
            return SourcePage(
                raw_records=[{"id": "raw-a"}],
                observations=[{"observation_id": "obs-a", "raw_ref": None}],
                next_state={"cursor": "B"},
                observed_at="2026-08-29T17:00:00Z",
            )
        if cursor == "B":
            if self.fail_on_b:
                raise RuntimeError("synthetic provider failure")
            return SourcePage(
                raw_records=[{"id": "raw-b"}],
                observations=[{"observation_id": "obs-b", "raw_ref": None}],
                next_state=None,
                observed_at="2026-08-29T17:01:00Z",
            )
        raise AssertionError(f"unexpected cursor {cursor}")


class CollectionRunnerTests(unittest.IsolatedAsyncioTestCase):
    async def test_failure_resumes_from_last_committed_page(self):
        checkpoints = MemoryCheckpointStore()
        with tempfile.TemporaryDirectory() as tempdir:
            runner = CollectionRunner(
                checkpoints=checkpoints,
                raw_sink=JsonlGzipRawSink(tempdir),
            )
            source = FakeSource(fail_on_b=True)

            with self.assertRaisesRegex(RuntimeError, "synthetic provider failure"):
                await runner.run(source, "query")

            checkpoint = await checkpoints.load("fake", "fake:query")
            self.assertIsNotNone(checkpoint)
            self.assertEqual({"cursor": "B"}, checkpoint.state["continuation"])
            self.assertEqual(1, checkpoint.state["pages_completed"])
            self.assertEqual(1, checkpoint.state["observations_completed"])
            self.assertFalse(checkpoint.state["complete"])

            source.fail_on_b = False
            source.calls.clear()
            result = await runner.run(source, "query")

            self.assertTrue(result.resumed)
            self.assertTrue(result.complete)
            self.assertEqual(["B"], source.calls)
            self.assertEqual(1, result.pages_collected)
            self.assertEqual(1, result.observations_collected)
            self.assertEqual("obs-b", result.observations[0]["observation_id"])
            self.assertTrue(result.observations[0]["raw_ref"].startswith("file:"))

            final_checkpoint = await checkpoints.load("fake", "fake:query")
            self.assertTrue(final_checkpoint.state["complete"])
            self.assertIsNone(final_checkpoint.state["continuation"])
            self.assertEqual(2, final_checkpoint.state["pages_completed"])
            self.assertEqual(2, final_checkpoint.state["observations_completed"])

            raw_files = list(Path(tempdir).glob("raw/fake/*/*/*/*.jsonl.gz"))
            self.assertEqual(2, len(raw_files))

    async def test_completed_checkpoint_is_noop(self):
        checkpoints = MemoryCheckpointStore()
        with tempfile.TemporaryDirectory() as tempdir:
            runner = CollectionRunner(
                checkpoints=checkpoints,
                raw_sink=JsonlGzipRawSink(tempdir),
            )
            source = FakeSource()
            first = await runner.run(source, "done")
            self.assertTrue(first.complete)

            source.calls.clear()
            second = await runner.run(source, "done")
            self.assertTrue(second.complete)
            self.assertTrue(second.resumed)
            self.assertEqual([], source.calls)
            self.assertEqual(0, second.pages_collected)
            self.assertEqual([], second.observations)


if __name__ == "__main__":
    unittest.main()
