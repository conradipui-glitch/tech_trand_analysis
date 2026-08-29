import gzip
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

from tech_trend_analysis.storage.checkpoints import FileCheckpointStore, MemoryCheckpointStore
from tech_trend_analysis.storage.raw import JsonlGzipRawSink


class CheckpointStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_roundtrip(self):
        store = MemoryCheckpointStore()
        self.assertIsNone(await store.load("openalex", "query-1"))
        saved = await store.save("openalex", "query-1", {"cursor": "abc"})
        loaded = await store.load("openalex", "query-1")
        self.assertEqual(saved, loaded)
        await store.delete("openalex", "query-1")
        self.assertIsNone(await store.load("openalex", "query-1"))

    async def test_file_roundtrip_and_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = FileCheckpointStore(temp_dir)
            await store.save(
                "openalex",
                "neuromorphic/rolling-window",
                {"last_success_at": "2026-08-28T00:00:00Z"},
                updated_at="2026-08-29T00:00:00Z",
            )
            first = await store.load("openalex", "neuromorphic/rolling-window")
            self.assertEqual("2026-08-28T00:00:00Z", first.state["last_success_at"])

            await store.save(
                "openalex",
                "neuromorphic/rolling-window",
                {"last_success_at": "2026-08-29T00:00:00Z"},
                updated_at="2026-08-29T01:00:00Z",
            )
            second = await store.load("openalex", "neuromorphic/rolling-window")
            self.assertEqual("2026-08-29T00:00:00Z", second.state["last_success_at"])

            files = list(Path(temp_dir).rglob("*.json"))
            self.assertEqual(1, len(files))
            self.assertNotIn("neuromorphic", files[0].name)


class RawSinkTests(unittest.IsolatedAsyncioTestCase):
    async def test_jsonl_gzip_roundtrip(self):
        records = [
            {"id": "W1", "title": "Первый"},
            {"id": "W2", "title": "Second"},
        ]
        with tempfile.TemporaryDirectory() as temp_dir:
            sink = JsonlGzipRawSink(temp_dir)
            ref = await sink.write_batch(
                "openalex",
                records,
                observed_at="2026-08-29T12:34:56Z",
                batch_id="page-0001",
            )

            self.assertEqual(2, ref.record_count)
            self.assertEqual("page-0001", ref.batch_id)
            self.assertEqual(64, len(ref.sha256))

            path = Path(urlparse(ref.uri).path)
            self.assertTrue(path.exists())
            self.assertEqual(
                ("raw", "openalex", "2026", "08", "29", "page-0001.jsonl.gz"),
                path.parts[-6:],
            )
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                loaded = [json.loads(line) for line in handle if line.strip()]
            self.assertEqual(records, loaded)

    async def test_empty_batch_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            sink = JsonlGzipRawSink(temp_dir)
            with self.assertRaises(ValueError):
                await sink.write_batch("openalex", [])


if __name__ == "__main__":
    unittest.main()
