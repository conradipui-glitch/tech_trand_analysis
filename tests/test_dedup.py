import unittest

from tech_trend_analysis.dedup import ObservationDeduplicator


def observation(
    observation_id: str,
    *,
    provider: str,
    external_id: str,
    title: str,
    text: str | None = None,
    evidence_type: str = "research",
    artifact_kind: str = "paper",
    canonical_url: str | None = None,
    actor: str | None = "Example Lab",
):
    actors = []
    if actor:
        actors.append(
            {
                "name": actor,
                "kind": "institution",
                "external_id": None,
                "country": None,
            }
        )
    return {
        "observation_id": observation_id,
        "provider": provider,
        "external_id": external_id,
        "evidence_type": evidence_type,
        "artifact_kind": artifact_kind,
        "title": title,
        "text": text,
        "canonical_url": canonical_url,
        "actors": actors,
        "fingerprints": {
            "canonical_key": None,
            "content_hash": None,
            "simhash": None,
        },
    }


class DedupTests(unittest.TestCase):
    def test_same_doi_collapses_across_providers(self):
        dedup = ObservationDeduplicator()
        first = observation(
            "openalex:W1",
            provider="openalex",
            external_id="W1",
            title="A new neuromorphic device",
            text="Paper abstract.",
            canonical_url="https://doi.org/10.1234/example",
        )
        second = observation(
            "crossref:X1",
            provider="crossref",
            external_id="X1",
            title="A new neuromorphic device",
            text="Different metadata rendering.",
            canonical_url="doi:10.1234/example",
        )

        result = dedup.add_batch([first, second])

        self.assertEqual(["openalex:W1"], [item["observation_id"] for item in result.unique])
        self.assertEqual(1, len(result.duplicates))
        self.assertEqual("crossref:X1", result.duplicates[0].observation_id)
        self.assertEqual("openalex:W1", result.duplicates[0].duplicate_of)
        self.assertEqual("exact", result.duplicates[0].reason)

    def test_tracking_parameters_do_not_create_new_artifact(self):
        dedup = ObservationDeduplicator()
        first = observation(
            "web:1",
            provider="web",
            external_id="1",
            title="Photonic chip announcement",
            text="Version one.",
            artifact_kind="webpage",
            evidence_type="product",
            canonical_url="https://example.com/chip?item=42&utm_source=newsletter",
        )
        second = observation(
            "web:2",
            provider="web",
            external_id="2",
            title="Photonic chip announcement mirror",
            text="Version two.",
            artifact_kind="webpage",
            evidence_type="product",
            canonical_url="https://example.com/chip?item=42",
        )

        result = dedup.add_batch([first, second])
        self.assertEqual(1, len(result.unique))
        self.assertEqual("exact", result.duplicates[0].reason)

    def test_fuzzy_title_collapses_same_evidence_artifact(self):
        dedup = ObservationDeduplicator()
        first = observation(
            "paper:1",
            provider="openalex",
            external_id="1",
            title="Neuromorphic Edge Computing for Ultra-Low-Power AI Systems",
            text="First abstract version.",
        )
        second = observation(
            "paper:2",
            provider="other_research",
            external_id="2",
            title="Neuromorphic edge computing for ultra low power AI systems",
            text="A separately formatted abstract version.",
        )

        result = dedup.add_batch([first, second])
        self.assertEqual(1, len(result.unique))
        self.assertEqual(1, len(result.duplicates))
        self.assertEqual("fuzzy_title", result.duplicates[0].reason)

    def test_research_and_implementation_are_not_fuzzy_duplicates(self):
        dedup = ObservationDeduplicator()
        paper = observation(
            "paper:1",
            provider="openalex",
            external_id="1",
            title="Neuromorphic Edge Computing for Ultra-Low-Power AI Systems",
            text="Research paper.",
            evidence_type="research",
            artifact_kind="paper",
        )
        repo = observation(
            "github:1",
            provider="github",
            external_id="1",
            title="Neuromorphic Edge Computing for Ultra-Low-Power AI Systems",
            text="Reference implementation.",
            evidence_type="implementation",
            artifact_kind="repository",
        )

        result = dedup.add_batch([paper, repo])
        self.assertEqual(2, len(result.unique))
        self.assertEqual([], result.duplicates)

    def test_actor_disagreement_blocks_fuzzy_collapse(self):
        dedup = ObservationDeduplicator()
        first = observation(
            "paper:1",
            provider="openalex",
            external_id="1",
            title="Adaptive optical computing for edge inference",
            text="A.",
            actor="Lab A",
        )
        second = observation(
            "paper:2",
            provider="other_research",
            external_id="2",
            title="Adaptive optical computing for edge inference",
            text="B.",
            actor="Lab B",
        )

        result = dedup.add_batch([first, second])
        self.assertEqual(2, len(result.unique))
        self.assertEqual([], result.duplicates)

    def test_fingerprints_are_added_to_unique_observation(self):
        dedup = ObservationDeduplicator()
        item = observation(
            "paper:1",
            provider="openalex",
            external_id="1",
            title="New computing substrate",
            text="Evidence body.",
        )
        result = dedup.add_batch([item])
        fingerprints = result.unique[0]["fingerprints"]
        self.assertEqual(64, len(fingerprints["content_hash"]))
        self.assertEqual(16, len(fingerprints["simhash"]))


if __name__ == "__main__":
    unittest.main()
