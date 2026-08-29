import unittest
from pathlib import Path

from tech_trend_analysis.evaluation import (
    evaluate_vectors,
    load_benchmark_dataset,
    run_embedding_benchmark,
)

ROOT = Path(__file__).resolve().parents[1]


class OracleProvider:
    name = "oracle-test-provider"

    def __init__(self, dataset):
        clusters = sorted({row["cluster"] for row in dataset.documents})
        self.index = {cluster: position for position, cluster in enumerate(clusters)}
        self.dimension = len(clusters)
        self.text_to_cluster = {row["text"]: row["cluster"] for row in dataset.documents}
        self.text_to_cluster.update({row["query"]: row["target_cluster"] for row in dataset.queries})

    def embed(self, texts, *, mode):
        vectors = []
        for text in texts:
            cluster = self.text_to_cluster[text]
            vector = [0.0] * self.dimension
            vector[self.index[cluster]] = 1.0
            vectors.append(vector)
        return vectors


class EmbeddingBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dataset = load_benchmark_dataset(ROOT / "evaluation")
        cls.clusters = sorted({row["cluster"] for row in cls.dataset.documents})
        cls.index = {cluster: position for position, cluster in enumerate(cls.clusters)}

    def one_hot(self, cluster):
        vector = [0.0] * len(self.clusters)
        vector[self.index[cluster]] = 1.0
        return vector

    def test_oracle_vectors_produce_expected_metrics(self):
        document_vectors = {
            row["id"]: self.one_hot(row["cluster"])
            for row in self.dataset.documents
        }
        query_vectors = {
            row["id"]: self.one_hot(row["target_cluster"])
            for row in self.dataset.queries
        }
        metrics = evaluate_vectors(self.dataset, document_vectors, query_vectors)

        self.assertEqual(12, metrics["dimension"])
        self.assertAlmostEqual(0.25, metrics["recall_at_1"])
        self.assertAlmostEqual(0.75, metrics["recall_at_3"])
        self.assertAlmostEqual(1.0, metrics["recall_at_5"])
        self.assertAlmostEqual(1.0, metrics["mrr"])
        self.assertAlmostEqual(1.0, metrics["hard_negative_win_rate"])
        self.assertAlmostEqual(1.0, metrics["pair_ordering_accuracy"])
        self.assertAlmostEqual(1.0, metrics["ru_mrr"])
        self.assertAlmostEqual(1.0, metrics["en_mrr"])

    def test_run_benchmark_uses_provider_contract(self):
        report = run_embedding_benchmark(OracleProvider(self.dataset), self.dataset)
        self.assertEqual("oracle-test-provider", report.provider)
        self.assertEqual(12, report.dimension)
        self.assertEqual(48, report.document_count)
        self.assertEqual(24, report.query_count)
        self.assertAlmostEqual(1.0, report.mrr)
        self.assertAlmostEqual(1.0, report.pair_ordering_accuracy)

    def test_rejects_inconsistent_dimensions(self):
        document_vectors = {
            row["id"]: self.one_hot(row["cluster"])
            for row in self.dataset.documents
        }
        query_vectors = {
            row["id"]: self.one_hot(row["target_cluster"])
            for row in self.dataset.queries
        }
        first_id = self.dataset.documents[0]["id"]
        document_vectors[first_id] = [1.0, 0.0]
        with self.assertRaisesRegex(ValueError, "inconsistent dimensions"):
            evaluate_vectors(self.dataset, document_vectors, query_vectors)


if __name__ == "__main__":
    unittest.main()
