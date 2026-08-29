import unittest
from datetime import date

from tech_trend_analysis.backfill import (
    AdaptiveBackfillPlanner,
    BackfillPlan,
    gate_historical_vectors,
)
from tech_trend_analysis.trend_state import TrendState


def state(*, first_seen: str = "2026-01-01T00:00:00Z") -> TrendState:
    return TrendState(
        trend_id="trend:software_ai:test",
        profile="software_ai",
        technology_direction="AI agents",
        embedding_model="BAAI/bge-m3",
        centroid=(1.0, 0.0),
        first_seen=first_seen,
        last_seen="2026-08-01T00:00:00Z",
        created_at="2026-08-29T00:00:00Z",
        updated_at="2026-08-29T00:00:00Z",
        observation_ids={"o1", "o2", "o3"},
    )


def observations():
    return {
        "o1": {
            "observation_id": "o1",
            "title": "Persistent memory for autonomous AI agents",
            "text": "Long-term memory lets software agents retain state between tasks.",
            "source_topics": ["AI Agents", "Machine Learning"],
            "classifications": [{"scheme": "topic", "value": "T1", "label": "AI Agents"}],
        },
        "o2": {
            "observation_id": "o2",
            "title": "Long-term memory systems for agent workflows",
            "text": "Agent memory stores episodes and retrieves context for later actions.",
            "source_topics": ["AI Agents"],
            "classifications": [{"scheme": "topic", "value": "T1", "label": "AI Agents"}],
        },
        "o3": {
            "observation_id": "o3",
            "title": "Stateful memory architecture for LLM agents",
            "text": "Persistent state and memory retrieval improve multi-step agent behavior.",
            "source_topics": ["AI Agents", "Language Models"],
            "classifications": [{"scheme": "topic", "value": "T2", "label": "Language Models"}],
        },
    }


class AdaptiveBackfillPlannerTests(unittest.TestCase):
    def test_descriptor_uses_real_evidence_and_common_topics(self):
        planner = AdaptiveBackfillPlanner()
        descriptor = planner.build_descriptor(state(), observations())

        self.assertIn(descriptor.representative_title, {item["title"] for item in observations().values()})
        self.assertTrue(descriptor.query_text.startswith(descriptor.representative_title))
        self.assertEqual("AI Agents", descriptor.source_topics[0])
        self.assertEqual("AI Agents", descriptor.classifications[0])

    def test_initial_software_window_is_bounded(self):
        planner = AdaptiveBackfillPlanner()
        current = state()
        descriptor = planner.build_descriptor(current, observations())
        plan = planner.initial_plan(current, descriptor, as_of=date(2026, 8, 29))

        self.assertEqual(date(2024, 9, 1), plan.from_date)
        self.assertEqual(date(2026, 8, 29), plan.to_date)
        self.assertEqual(date(2021, 9, 1), plan.max_history_start)
        self.assertEqual("initial_bounded_window", plan.reason)

    def test_expands_backward_only_when_signal_touches_left_boundary(self):
        planner = AdaptiveBackfillPlanner()
        near_boundary = state(first_seen="2024-09-20T00:00:00Z")
        descriptor = planner.build_descriptor(near_boundary, observations())
        plan = planner.initial_plan(near_boundary, descriptor, as_of=date(2026, 8, 29))

        self.assertTrue(planner.should_expand(near_boundary, plan))
        older = planner.expand(near_boundary, plan)
        self.assertIsNotNone(older)
        assert older is not None
        self.assertEqual(date(2023, 9, 1), older.from_date)
        self.assertEqual(date(2024, 8, 31), older.to_date)
        self.assertEqual(1, older.iteration)
        self.assertEqual("left_boundary_signal", older.reason)

        safely_inside = state(first_seen="2025-03-01T00:00:00Z")
        self.assertFalse(planner.should_expand(safely_inside, plan))
        self.assertIsNone(planner.expand(safely_inside, plan))

    def test_expansion_never_crosses_max_history_start(self):
        planner = AdaptiveBackfillPlanner()
        current = state(first_seen="2021-10-01T00:00:00Z")
        plan = BackfillPlan(
            trend_id=current.trend_id,
            provider="openalex",
            technology_direction=current.technology_direction,
            source_profile=current.profile,
            query_text="agent memory",
            from_date=date(2021, 10, 1),
            to_date=date(2022, 9, 30),
            iteration=4,
            reason="left_boundary_signal",
            max_history_start=date(2021, 9, 1),
        )
        expanded = planner.expand(current, plan)
        self.assertIsNotNone(expanded)
        assert expanded is not None
        self.assertEqual(date(2021, 9, 1), expanded.from_date)
        self.assertEqual(date(2021, 9, 30), expanded.to_date)

        final_state = state(first_seen="2021-09-05T00:00:00Z")
        self.assertFalse(planner.should_expand(final_state, expanded))

    def test_openalex_plan_reuses_trend_specific_descriptor(self):
        planner = AdaptiveBackfillPlanner()
        current = state()
        descriptor = planner.build_descriptor(current, observations())
        plan = planner.initial_plan(current, descriptor, as_of=date(2026, 8, 29))
        query = planner.to_openalex_query(plan, per_page=50, max_pages=7)

        self.assertEqual(plan.query_text, query.query_text)
        self.assertEqual(plan.from_date, query.from_date)
        self.assertEqual(plan.to_date, query.to_date)
        self.assertEqual(50, query.per_page)
        self.assertEqual(7, query.max_pages)
        self.assertTrue(query.query_id.startswith("backfill:"))

    def test_historical_gate_rejects_adjacent_geometry(self):
        current = state()
        gated = gate_historical_vectors(
            current,
            observation_ids=["same", "near", "adjacent"],
            vectors=[
                [1.0, 0.0],
                [0.95, 0.20],
                [0.0, 1.0],
            ],
            similarity_threshold=0.82,
        )

        self.assertEqual(("same", "near"), gated.accepted_ids)
        self.assertEqual(("adjacent",), gated.rejected_ids)
        self.assertGreater(gated.similarities["near"], 0.9)
        self.assertLess(gated.similarities["adjacent"], 0.1)


if __name__ == "__main__":
    unittest.main()
