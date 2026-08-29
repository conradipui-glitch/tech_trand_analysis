import json
import unittest
from datetime import date
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from tech_trend_analysis.result_assembler import CoverageStatus, assemble_trend_analysis
from tech_trend_analysis.trend_state import PeriodBucket, TrendState


class ResultAssemblerTests(unittest.TestCase):
    def _state(self, trend_id: str, counts: list[int], *, first_seen: str) -> TrendState:
        months = ["2026-03", "2026-04", "2026-05", "2026-06", "2026-07", "2026-08"]
        periods = {}
        for month, count in zip(months, counts, strict=True):
            if count:
                periods[month] = PeriodBucket(
                    period=month,
                    total=count,
                    by_evidence_type={"research": max(1, count // 2), "implementation": count - max(1, count // 2)} if count > 1 else {"research": 1},
                    by_provider={"openalex": max(1, count // 2), "github": max(0, count - max(1, count // 2))},
                )
        return TrendState(
            trend_id=trend_id,
            profile="software_ai",
            technology_direction="AI agents",
            embedding_model="bge-m3",
            centroid=(1.0, 0.0),
            first_seen=first_seen,
            last_seen="2026-08-20T00:00:00Z",
            created_at="2026-03-01T00:00:00Z",
            updated_at="2026-08-20T00:00:00Z",
            observation_ids={f"{trend_id}:obs:{i}" for i in range(6)},
            evidence_counts={"research": 3, "implementation": 3},
            provider_counts={"openalex": 3, "github": 3},
            artifact_counts={"paper": 3, "repository": 3},
            actor_keys={f"actor:{i}" for i in range(6)},
            first_evidence_at={
                "research": first_seen,
                "implementation": "2026-05-01T00:00:00Z",
            },
            periods=periods,
        )

    def _observation(self, state: TrendState, *, title: str, evidence_type: str = "implementation"):
        observation_id = sorted(state.observation_ids)[0]
        return observation_id, {
            "schema_version": "0.2.0",
            "observation_id": observation_id,
            "provider": "github" if evidence_type == "implementation" else "openalex",
            "evidence_type": evidence_type,
            "artifact_kind": "repository" if evidence_type == "implementation" else "paper",
            "canonical_url": f"https://example.test/{observation_id}",
            "title": title,
            "text": f"Grounded description for {title}",
            "published_at": "2026-07-01T00:00:00Z",
            "actors": [{"name": "Example Lab", "country": "AT"}],
            "metrics": {"stars": 100},
            "analysis": {"technology_labels": []},
        }

    def test_assembler_ranks_by_score_and_validates_schema(self):
        fast = self._state("trend:fast", [1, 1, 2, 4, 8, 16], first_seen="2026-03-01T00:00:00Z")
        flat = self._state("trend:flat", [4, 4, 4, 4, 4, 4], first_seen="2024-01-01T00:00:00Z")
        observations = dict([
            self._observation(fast, title="Agent browser control"),
            self._observation(flat, title="Mature browser automation"),
        ])

        result = assemble_trend_analysis(
            technology_direction="AI agents",
            normalized_direction="AI agent technologies",
            source_profile="software_ai",
            candidates=[flat, fast],
            observations_by_id=observations,
            as_of=date(2026, 8, 29),
            generated_at="2026-08-29T20:00:00Z",
            coverage=CoverageStatus(
                attempted=("github", "openalex", "epo_ops"),
                succeeded=("github", "openalex"),
                failed=("epo_ops",),
            ),
        )

        self.assertEqual("partial", result["summary"]["status"])
        self.assertEqual(2, result["summary"]["trend_count"])
        self.assertEqual("trend:fast", result["trends"][0]["trend_id"])
        self.assertEqual(1, result["trends"][0]["rank"])
        self.assertIn("Недостаточно", result["trends"][0]["motivation"]["problem"])
        self.assertIn("epo_ops", result["summary"]["coverage"]["failed"])

        schema = json.loads(Path("schemas/trend-result.schema.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(result)

    def test_candidate_without_grounded_source_is_skipped_not_fabricated(self):
        state = self._state("trend:no-source", [1, 2, 3, 4, 5, 6], first_seen="2026-03-01T00:00:00Z")
        result = assemble_trend_analysis(
            technology_direction="AI agents",
            source_profile="software_ai",
            candidates=[state],
            observations_by_id={},
            as_of=date(2026, 8, 29),
            generated_at="2026-08-29T20:00:00Z",
        )
        self.assertEqual("insufficient_evidence", result["summary"]["status"])
        self.assertEqual([], result["trends"])
        self.assertTrue(any("no representative source" in warning for warning in result["summary"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
