import json
import unittest

from tech_trend_analysis.analyst import AnalystError, build_messages, parse_narrative, source_refs


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
        self.assertIn("not financial advice", system)

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
        result = parse_narrative(json.dumps(payload, ensure_ascii=False), allowed_source_refs=source_refs(self.trend))
        self.assertEqual("Краткое объяснение.", result.human_summary)
        self.assertEqual(2, len(result.used_source_refs))

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
