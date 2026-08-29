import json
import unittest

from tech_trend_analysis.analyst import (
    AnalystError,
    INSUFFICIENT_PROBLEM_EVIDENCE,
    build_messages,
    has_problem_advantage_evidence,
    parse_narrative,
    source_refs,
)


class AnalystTests(unittest.TestCase):
    def setUp(self):
        self.trend = {
            "trend_id": "t-1",
            "label": "Example trend",
            "score": {"total": 72.0, "confidence": 0.61},
            "evidence": [
                {"observation_id": "obs-1", "url": "https://example.test/1", "evidence_type": "research"},
                {"observation_id": "obs-2", "url": "https://example.test/2", "evidence_type": "implementation"},
            ],
        }

    def test_prompt_forbids_ranking_changes_and_invention(self):
        messages = build_messages(self.trend)
        system = messages[0]["content"]
        self.assertIn("not you", system)
        self.assertIn("Never invent", system)
        self.assertIn("Do not change score", system)
        self.assertIn("general knowledge is forbidden", system)
        self.assertIn("not financial advice", system)
        self.assertIn(INSUFFICIENT_PROBLEM_EVIDENCE, system)

    def test_source_refs_are_collected_from_input_only(self):
        refs = source_refs(self.trend)
        self.assertIn("obs-1", refs)
        self.assertIn("https://example.test/2", refs)

    def test_valid_grounded_json_is_accepted(self):
        payload = {
            "human_summary": "Краткое объяснение.",
            "why_now": "Есть рост подтверждённого evidence.",
            "problem_advantage": "Решает указанную в evidence проблему.",
            "caveat": "История пока короткая.",
            "what_to_watch_next": "Следить за implementation evidence.",
            "analyst_note": "Полезно проверить переход research → implementation.",
            "used_source_refs": ["obs-1", "https://example.test/2"],
        }
        result = parse_narrative(
            json.dumps(payload, ensure_ascii=False),
            allowed_source_refs=source_refs(self.trend),
            problem_advantage_supported=True,
        )
        self.assertEqual("Краткое объяснение.", result.human_summary)
        self.assertEqual("Решает указанную в evidence проблему.", result.problem_advantage)
        self.assertEqual(2, len(result.used_source_refs))

    def test_unsupported_problem_advantage_is_overridden_fail_closed(self):
        payload = {
            "human_summary": "Кратко.",
            "why_now": "По метрикам есть изменение.",
            "problem_advantage": "Модель придумала красивую возможность.",
            "caveat": "Есть ограничение.",
            "what_to_watch_next": "Проверить следующий evidence.",
            "analyst_note": "Гипотеза для проверки.",
            "used_source_refs": ["obs-1"],
        }
        result = parse_narrative(
            json.dumps(payload, ensure_ascii=False),
            allowed_source_refs=source_refs(self.trend),
            problem_advantage_supported=False,
        )
        self.assertEqual(INSUFFICIENT_PROBLEM_EVIDENCE, result.problem_advantage)
        self.assertFalse(has_problem_advantage_evidence(self.trend))

    def test_explicit_problem_evidence_enables_rewrite(self):
        trend = dict(self.trend)
        trend["problem_advantage_evidence"] = {
            "statement": "Validated evidence statement",
            "source_ref": "obs-1",
        }
        self.assertTrue(has_problem_advantage_evidence(trend))
        self.assertIn("explicit problem_advantage_evidence", build_messages(trend)[0]["content"])

    def test_unknown_citation_is_rejected(self):
        payload = {
            "human_summary": "x", "why_now": "x", "problem_advantage": "x",
            "caveat": "x", "what_to_watch_next": "x", "analyst_note": "x",
            "used_source_refs": ["invented-source"],
        }
        with self.assertRaisesRegex(AnalystError, "unknown source refs"):
            parse_narrative(json.dumps(payload), allowed_source_refs=source_refs(self.trend))


if __name__ == "__main__":
    unittest.main()
