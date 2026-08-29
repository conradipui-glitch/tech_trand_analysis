import unittest
from datetime import date

from scripts.run_retrospective_validation import (
    _aggregate_state,
    _first_sustained_period,
    _lead_months,
    month_windows,
)
from tech_trend_analysis.scoring import EmergingScorer


class RetrospectiveValidationTests(unittest.TestCase):
    def test_month_windows_cap_last_month_at_milestone_day(self):
        windows = list(month_windows(date(2022, 11, 1), date(2023, 2, 17)))
        self.assertEqual(["2022-11", "2022-12", "2023-01", "2023-02"], [item.key for item in windows])
        self.assertEqual(date(2023, 2, 17), windows[-1].end)

    def test_isolated_hit_does_not_become_sustained_signal(self):
        curve = [
            {"period": "2020-01", "total_count": 1},
            {"period": "2020-02", "total_count": 0},
            {"period": "2020-03", "total_count": 0},
            {"period": "2020-04", "total_count": 2},
            {"period": "2020-05", "total_count": 3},
        ]
        self.assertEqual("2020-04", _first_sustained_period(curve))
        self.assertIsNone(_first_sustained_period(curve[:4]))

    def test_first_seen_is_backdated_only_after_confirmation_exists(self):
        curve = [
            {"period": "2020-01", "total_count": 1},
            {"period": "2020-02", "total_count": 0},
            {"period": "2020-03", "total_count": 2},
        ]
        self.assertIsNone(_first_sustained_period(curve[:1]))
        self.assertIsNone(_first_sustained_period(curve[:2]))
        self.assertEqual("2020-01", _first_sustained_period(curve))

    def test_aggregate_state_uses_full_counts_not_sample_size(self):
        case = {
            "id": "demo",
            "profile": "software_ai",
            "technology_direction": "demo technology",
        }
        curve = [
            {
                "period": "2026-06",
                "total_count": 11,
                "research_count": 10,
                "implementation_count": 1,
                "openalex": {"sample_actors": ["oa:a", "oa:b"]},
                "github": {"sample_actors": ["gh:a"]},
            },
            {
                "period": "2026-07",
                "total_count": 22,
                "research_count": 20,
                "implementation_count": 2,
                "openalex": {"sample_actors": ["oa:b", "oa:c"]},
                "github": {"sample_actors": ["gh:b"]},
            },
        ]
        state = _aggregate_state(case, curve, first_sustained="2026-06")

        self.assertEqual(33, state.observation_count)
        self.assertEqual(30, state.evidence_counts["research"])
        self.assertEqual(3, state.evidence_counts["implementation"])
        self.assertEqual(11, state.periods["2026-06"].total)
        self.assertEqual(22, state.periods["2026-07"].total)
        self.assertEqual(5, state.actor_diversity)

    def test_aggregate_curve_can_feed_emerging_scorer(self):
        case = {
            "id": "demo",
            "profile": "software_ai",
            "technology_direction": "demo technology",
        }
        curve = []
        for month, research, implementation in [
            ("2026-03", 1, 0),
            ("2026-04", 2, 0),
            ("2026-05", 2, 1),
            ("2026-06", 3, 2),
            ("2026-07", 5, 4),
            ("2026-08", 8, 6),
        ]:
            curve.append(
                {
                    "period": month,
                    "total_count": research + implementation,
                    "research_count": research,
                    "implementation_count": implementation,
                    "openalex": {"sample_actors": [f"oa:{month}"]},
                    "github": {"sample_actors": [f"gh:{month}"] if implementation else []},
                }
            )
        state = _aggregate_state(case, curve, first_sustained="2026-03")
        score = EmergingScorer().score(state, as_of=date(2026, 8, 29))
        self.assertGreater(score.total, 60)
        self.assertGreater(score.confidence, 0.6)

    def test_lead_months_is_month_level_and_pre_milestone_positive(self):
        self.assertEqual(5, _lead_months("2022-06", date(2022, 11, 25)))
        self.assertEqual(0, _lead_months("2022-11", date(2022, 11, 25)))
        self.assertEqual(-1, _lead_months("2022-12", date(2022, 11, 25)))


if __name__ == "__main__":
    unittest.main()
