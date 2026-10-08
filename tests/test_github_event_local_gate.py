import unittest

from tech_trend_analysis.evaluation.github_event_local_benchmark import evaluate_gold
from tech_trend_analysis.github_event_local_gate import evaluate_event_local


class GitHubEventLocalGateTests(unittest.TestCase):
    def test_all_labeled_events_are_classified_and_heldout_false_positives_are_zero(self):
        result = evaluate_gold()
        self.assertEqual(24, sum(v["count"] for v in result["by_split"].values()))
        for split in ("calibration", "holdout"):
            self.assertEqual(0, result["by_split"][split]["fp"], result["diagnostics"])
        self.assertGreaterEqual(result["by_split"]["holdout"]["recall"], 0.80, result["diagnostics"])

    def test_long_release_only_uses_actual_relevant_line(self):
        result = evaluate_event_local(
            technology_direction="low-rank adaptation of large language models",
            title="FlashAttention-2 and Baichuan2",
            text="FlashAttention-2 and Baichuan2\n- Support v2 tokenizer\n- Support --lora_target all for LoRA training on LLaMA models",
        )
        self.assertTrue(result.eligible)
        self.assertIn("lora_target", result.evidence_span)
        self.assertNotIn("FlashAttention", result.evidence_span)

    def test_unknown_technology_requires_review_instead_of_inventing_grounding(self):
        result = evaluate_event_local(
            technology_direction="neuromorphic processors",
            title="Add support", text="Implement neuromorphic mesh accelerators.",
        )
        self.assertEqual("review_required", result.status)
        self.assertFalse(result.eligible)


if __name__ == "__main__":
    unittest.main()
