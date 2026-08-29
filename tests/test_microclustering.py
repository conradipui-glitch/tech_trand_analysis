import unittest

import numpy as np

from tech_trend_analysis.clustering import (
    MicroclusterConfig,
    Microclusterer,
    PROFILE_CONFIGS,
)


class MicroclustererTests(unittest.TestCase):
    def test_dense_clusters_without_known_cluster_count(self):
        clusterer = Microclusterer(embedding_model="test-model")
        result = clusterer.cluster(
            profile="hardware_semiconductor",
            observation_ids=["a1", "a2", "b1", "b2"],
            texts=["alpha one", "alpha two", "beta one", "beta two"],
            vectors=[
                [1.0, 0.02, 0.0],
                [0.99, 0.04, 0.0],
                [0.01, 1.0, 0.0],
                [0.02, 0.99, 0.0],
            ],
            config=MicroclusterConfig(
                algorithm="agglomerative_average_cosine",
                distance_threshold=0.10,
                calibration="test",
            ),
        )
        self.assertEqual(2, len(result.clusters))
        self.assertEqual(result.assignments["a1"], result.assignments["a2"])
        self.assertEqual(result.assignments["b1"], result.assignments["b2"])
        self.assertNotEqual(result.assignments["a1"], result.assignments["b1"])
        self.assertEqual("test-model", result.embedding_model)

    def test_hybrid_can_split_lexically_distinct_dense_neighbors(self):
        clusterer = Microclusterer()
        # Dense vectors intentionally almost identical. With alpha=0.50 the
        # lexical term must be strong enough to merge each lexical pair while
        # keeping the two vocabularies apart. In this synthetic geometry the
        # within-pair hybrid distances are about 0.31-0.36 and cross-pair
        # distances are about 0.50, so 0.40 is the meaningful test threshold.
        result = clusterer.cluster(
            profile="software_ai",
            observation_ids=["browser-1", "browser-2", "code-1", "code-2"],
            texts=[
                "browser navigation clicks websites",
                "browser page navigation web clicks",
                "repository code tests compiler",
                "code repository tests software compiler",
            ],
            vectors=[
                [1.0, 0.02],
                [0.999, 0.025],
                [0.998, 0.03],
                [0.997, 0.035],
            ],
            config=MicroclusterConfig(
                algorithm="agglomerative_hybrid_dense_tfidf",
                distance_threshold=0.40,
                dense_alpha=0.50,
                calibration="test",
            ),
        )
        self.assertEqual(2, len(result.clusters))
        self.assertEqual(result.assignments["browser-1"], result.assignments["browser-2"])
        self.assertEqual(result.assignments["code-1"], result.assignments["code-2"])
        self.assertNotEqual(result.assignments["browser-1"], result.assignments["code-1"])

    def test_cluster_ids_are_stable_for_same_members(self):
        config = MicroclusterConfig(
            algorithm="agglomerative_average_cosine",
            distance_threshold=0.15,
            calibration="test",
        )
        clusterer = Microclusterer()
        first = clusterer.cluster(
            profile="hardware_semiconductor",
            observation_ids=["x2", "x1"],
            texts=["same topic two", "same topic one"],
            vectors=[[1.0, 0.01], [1.0, 0.02]],
            config=config,
        )
        second = clusterer.cluster(
            profile="hardware_semiconductor",
            observation_ids=["x1", "x2"],
            texts=["same topic one", "same topic two"],
            vectors=[[1.0, 0.02], [1.0, 0.01]],
            config=config,
        )
        self.assertEqual(first.clusters[0].cluster_id, second.clusters[0].cluster_id)
        self.assertEqual(("x1", "x2"), first.clusters[0].member_ids)

    def test_centroid_is_normalized(self):
        clusterer = Microclusterer()
        result = clusterer.cluster(
            profile="hardware_semiconductor",
            observation_ids=["x1", "x2"],
            texts=["x one", "x two"],
            vectors=[[2.0, 0.0], [1.0, 0.0]],
            config=MicroclusterConfig(
                algorithm="agglomerative_average_cosine",
                distance_threshold=0.1,
                calibration="test",
            ),
        )
        centroid = np.asarray(result.clusters[0].centroid)
        self.assertAlmostEqual(1.0, float(np.linalg.norm(centroid)), places=6)

    def test_default_profiles_are_explicitly_calibrated_or_marked_fallback(self):
        self.assertEqual("gold_v0_2026-08-29", PROFILE_CONFIGS["software_ai"].calibration)
        self.assertEqual("gold_v0_2026-08-29", PROFILE_CONFIGS["hardware_semiconductor"].calibration)
        self.assertIn("purity_first", PROFILE_CONFIGS["materials_energy"].calibration)
        self.assertEqual("fallback_unvalidated", PROFILE_CONFIGS["bio_medtech"].calibration)
        self.assertEqual("fallback_unvalidated", PROFILE_CONFIGS["mixed"].calibration)

    def test_rejects_zero_vectors(self):
        with self.assertRaisesRegex(ValueError, "zero vectors"):
            Microclusterer().cluster(
                profile="software_ai",
                observation_ids=["x"],
                texts=["text"],
                vectors=[[0.0, 0.0]],
            )


if __name__ == "__main__":
    unittest.main()
