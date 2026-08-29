import unittest
from datetime import date

from tech_trend_analysis.scoring import EmergingScorer
from tech_trend_analysis.trend_state import PeriodBucket, TrendState


AS_OF = date(2026, 8, 29)


def make_state(
    *,
    trend_id: str,
    profile: str,
    first_seen: str,
    last_seen: str,
    monthly_counts: dict[str, int],
    evidence_counts: dict[str, int],
    provider_counts: dict[str, int],
    actor_count: int,
    observation_count: int,
    first_evidence_at: dict[str, str] | None = None,
) -> TrendState:
    periods = {
        period: PeriodBucket(period=period, total=count)
        for period, count in monthly_counts.items()
    }
    return TrendState(
        trend_id=trend_id,
        profile=profile,
        technology_direction="test technology",
        embedding_model="BAAI/bge-m3",
        centroid=(1.0, 0.0),
        first_seen=first_seen,
        last_seen=last_seen,
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
        observation_ids={f"o{i}" for i in range(observation_count)},
        evidence_counts=dict(evidence_counts),
        provider_counts=dict(provider_counts),
        actor_keys={f"actor:{i}" for i in range(actor_count)},
        first_evidence_at=dict(first_evidence_at or {}),
        periods=periods,
    )


class EmergingScorerTests(unittest.TestCase):
    def setUp(self):
        self.scorer = EmergingScorer()

    def test_accelerating_multisource_trend_scores_high(self):
        state = make_state(
            trend_id="emerging",
            profile="hardware_semiconductor",
            first_seen="2026-03-01T00:00:00Z",
            last_seen="2026-08-20T00:00:00Z",
            monthly_counts={
                "2026-03": 1,
                "2026-04": 1,
                "2026-05": 2,
                "2026-06": 3,
                "2026-07": 5,
                "2026-08": 8,
            },
            evidence_counts={"research": 6, "patent": 4, "implementation": 10},
            provider_counts={"openalex": 6, "epo_ops": 4, "github": 10},
            actor_count=10,
            observation_count=20,
            first_evidence_at={
                "research": "2026-03-01T00:00:00Z",
                "patent": "2026-05-01T00:00:00Z",
                "implementation": "2026-06-01T00:00:00Z",
            },
        )
        score = self.scorer.score(state, as_of=AS_OF)

        self.assertGreater(score.total, 75)
        self.assertGreater(score.confidence, 0.75)
        self.assertEqual("emerging", score.stage)
        self.assertGreater(score.components["growth"].value, 75)
        self.assertEqual(0, score.components["maturity_penalty"].value)

    def test_one_month_research_spike_is_not_promoted_to_emerging(self):
        state = make_state(
            trend_id="spike",
            profile="software_ai",
            first_seen="2026-08-01T00:00:00Z",
            last_seen="2026-08-20T00:00:00Z",
            monthly_counts={"2026-08": 20},
            evidence_counts={"research": 20},
            provider_counts={"openalex": 20},
            actor_count=1,
            observation_count=20,
            first_evidence_at={"research": "2026-08-01T00:00:00Z"},
        )
        score = self.scorer.score(state, as_of=AS_OF)

        self.assertLess(score.total, 60)
        self.assertLess(score.confidence, 0.55)
        self.assertEqual("weak_signal", score.stage)
        self.assertLess(score.components["growth"].value, 50)
        self.assertLess(score.components["persistence"].value, 50)

    def test_mature_high_volume_topic_is_penalized(self):
        mature = make_state(
            trend_id="mature",
            profile="hardware_semiconductor",
            first_seen="2018-01-01T00:00:00Z",
            last_seen="2026-08-20T00:00:00Z",
            monthly_counts={
                "2025-09": 10,
                "2025-10": 10,
                "2025-11": 10,
                "2025-12": 10,
                "2026-01": 10,
                "2026-02": 10,
                "2026-03": 10,
                "2026-04": 10,
                "2026-05": 10,
                "2026-06": 10,
                "2026-07": 10,
                "2026-08": 10,
            },
            evidence_counts={
                "research": 40,
                "patent": 30,
                "implementation": 20,
                "product": 20,
                "adoption": 10,
            },
            provider_counts={"openalex": 40, "epo_ops": 30, "github": 20, "web": 30},
            actor_count=30,
            observation_count=120,
            first_evidence_at={
                "research": "2018-01-01T00:00:00Z",
                "patent": "2019-01-01T00:00:00Z",
                "implementation": "2020-01-01T00:00:00Z",
                "product": "2021-01-01T00:00:00Z",
                "adoption": "2022-01-01T00:00:00Z",
            },
        )
        score = self.scorer.score(mature, as_of=AS_OF)

        self.assertGreater(score.components["maturity_penalty"].value, 80)
        self.assertLess(score.total, 50)
        self.assertEqual("unknown", score.stage)

    def test_declining_signal_has_low_growth_and_acceleration(self):
        declining = make_state(
            trend_id="declining",
            profile="software_ai",
            first_seen="2025-12-01T00:00:00Z",
            last_seen="2026-08-01T00:00:00Z",
            monthly_counts={
                "2026-03": 8,
                "2026-04": 7,
                "2026-05": 6,
                "2026-06": 5,
                "2026-07": 3,
                "2026-08": 1,
            },
            evidence_counts={"research": 10, "implementation": 20},
            provider_counts={"openalex": 10, "github": 20},
            actor_count=8,
            observation_count=30,
            first_evidence_at={
                "research": "2025-12-01T00:00:00Z",
                "implementation": "2026-02-01T00:00:00Z",
            },
        )
        score = self.scorer.score(declining, as_of=AS_OF)

        self.assertLess(score.components["growth"].value, 35)
        self.assertLess(score.components["acceleration"].value, 35)

    def test_software_profile_does_not_require_patent_to_score_evidence_breadth(self):
        software = make_state(
            trend_id="software",
            profile="software_ai",
            first_seen="2026-02-01T00:00:00Z",
            last_seen="2026-08-01T00:00:00Z",
            monthly_counts={
                "2026-03": 1,
                "2026-04": 2,
                "2026-05": 2,
                "2026-06": 3,
                "2026-07": 4,
                "2026-08": 5,
            },
            evidence_counts={"research": 5, "implementation": 8, "adoption": 2},
            provider_counts={"openalex": 5, "github": 8, "web": 2},
            actor_count=7,
            observation_count=15,
            first_evidence_at={
                "research": "2026-02-01T00:00:00Z",
                "implementation": "2026-03-01T00:00:00Z",
                "adoption": "2026-07-01T00:00:00Z",
            },
        )
        score = self.scorer.score(software, as_of=AS_OF)

        self.assertGreaterEqual(score.components["evidence_diversity"].value, 90)

    def test_contract_components_are_bounded_and_complete(self):
        state = make_state(
            trend_id="contract",
            profile="software_ai",
            first_seen="2026-06-01T00:00:00Z",
            last_seen="2026-08-01T00:00:00Z",
            monthly_counts={"2026-06": 1, "2026-07": 2, "2026-08": 3},
            evidence_counts={"research": 2, "implementation": 4},
            provider_counts={"openalex": 2, "github": 4},
            actor_count=4,
            observation_count=6,
            first_evidence_at={
                "research": "2026-06-01T00:00:00Z",
                "implementation": "2026-07-01T00:00:00Z",
            },
        )
        score = self.scorer.score(state, as_of=AS_OF)
        contract = score.to_contract()

        expected = {
            "growth",
            "acceleration",
            "novelty",
            "recency",
            "evidence_diversity",
            "actor_diversity",
            "persistence",
            "maturity_penalty",
        }
        self.assertEqual(expected, set(contract["components"]))
        self.assertGreaterEqual(contract["total"], 0)
        self.assertLessEqual(contract["total"], 100)
        self.assertGreaterEqual(contract["confidence"], 0)
        self.assertLessEqual(contract["confidence"], 1)
        for component in contract["components"].values():
            self.assertGreaterEqual(component["value"], 0)
            self.assertLessEqual(component["value"], 100)


if __name__ == "__main__":
    unittest.main()
