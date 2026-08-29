import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "evaluation"


def load_jsonl(name: str):
    path = EVAL / name
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise AssertionError(f"invalid JSONL {name}:{line_number}: {exc}") from exc
    return rows


class EvaluationCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = load_jsonl("embedding_corpus.jsonl")
        cls.queries = load_jsonl("retrieval_queries.jsonl")
        cls.pairs = load_jsonl("pair_cases.jsonl")
        cls.docs_by_id = {row["id"]: row for row in cls.documents}
        cls.pairs_by_id = {row["id"]: row for row in cls.pairs}

    def test_expected_size_and_coverage(self):
        self.assertEqual(48, len(self.documents))
        self.assertEqual(24, len(self.queries))
        self.assertEqual(24, len(self.pairs))
        self.assertEqual(48, len(self.docs_by_id))

        profiles = Counter(row["profile"] for row in self.documents)
        self.assertEqual(
            {"software_ai": 16, "hardware_semiconductor": 16, "materials_energy": 16},
            dict(profiles),
        )

        clusters = Counter((row["profile"], row["cluster"]) for row in self.documents)
        self.assertEqual(12, len(clusters))
        self.assertTrue(all(count == 4 for count in clusters.values()))

        languages = Counter(row["language"] for row in self.documents)
        self.assertEqual({"en": 36, "ru": 12}, dict(languages))
        self.assertEqual({"en": 12, "ru": 12}, dict(Counter(q["language"] for q in self.queries)))

    def test_retrieval_labels_reference_real_documents(self):
        for query in self.queries:
            relevant = query["relevant_ids"]
            hard_negative = query["hard_negative_ids"]
            self.assertGreaterEqual(len(relevant), 3)
            self.assertGreaterEqual(len(hard_negative), 2)
            self.assertTrue(set(relevant).isdisjoint(hard_negative))

            for doc_id in relevant + hard_negative:
                self.assertIn(doc_id, self.docs_by_id)
                self.assertEqual(query["profile"], self.docs_by_id[doc_id]["profile"])

            self.assertTrue(
                all(self.docs_by_id[doc_id]["cluster"] == query["target_cluster"] for doc_id in relevant)
            )
            self.assertTrue(
                all(self.docs_by_id[doc_id]["cluster"] != query["target_cluster"] for doc_id in hard_negative)
            )

    def test_each_cluster_has_en_and_ru_query(self):
        seen = defaultdict(set)
        for query in self.queries:
            seen[(query["profile"], query["target_cluster"])].add(query["language"])
        self.assertEqual(12, len(seen))
        self.assertTrue(all(languages == {"en", "ru"} for languages in seen.values()))

    def test_pair_cases_are_consistent(self):
        self.assertEqual(24, len(self.pairs_by_id))
        positives = [row for row in self.pairs if row["label"] == "same_technology"]
        negatives = [row for row in self.pairs if row["label"] == "adjacent_distinct"]
        self.assertEqual(12, len(positives))
        self.assertEqual(12, len(negatives))

        for pair in self.pairs:
            left = self.docs_by_id[pair["left_id"]]
            right = self.docs_by_id[pair["right_id"]]
            self.assertEqual(left["profile"], right["profile"])
            if pair["label"] == "same_technology":
                self.assertEqual(left["cluster"], right["cluster"])
                comparison_id = pair["expected_more_similar_than"]
                self.assertIn(comparison_id, self.pairs_by_id)
                self.assertEqual("adjacent_distinct", self.pairs_by_id[comparison_id]["label"])
            else:
                self.assertNotEqual(left["cluster"], right["cluster"])


if __name__ == "__main__":
    unittest.main()
