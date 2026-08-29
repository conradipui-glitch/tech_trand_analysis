import unittest

from tech_trend_analysis.history_filter import gate_sampled_count


class HistoryFilterTests(unittest.TestCase):
    def test_rejects_broad_pre_origin_keyword_noise(self):
        result = gate_sampled_count(
            raw_count=500,
            sample_texts=[
                "Document retrieval for question answering",
                "Augmented text generation with external features",
                "Information retrieval evaluation benchmark",
                "Neural generation systems",
                "Retrieval methods for digital libraries",
            ],
            anchor_text="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            aliases=("retrieval augmented generation", "rag"),
            context_terms=("knowledge", "language model", "nlp", "retrieval"),
        )
        self.assertEqual(0, result.estimated_count)
        self.assertEqual(0, result.matched_sample_count)

    def test_accepts_rag_cluster_samples_and_scales_only_relevant_fraction(self):
        result = gate_sampled_count(
            raw_count=100,
            sample_texts=[
                "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                "RAG for language model question answering",
                "Retrieval augmented generation with dense passage retrieval",
                "Generic neural generation systems",
                "Information retrieval benchmark",
            ],
            anchor_text="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
            aliases=("retrieval augmented generation", "rag"),
            context_terms=("knowledge", "language model", "nlp", "retrieval"),
        )
        self.assertGreaterEqual(result.matched_sample_count, 3)
        self.assertGreater(result.estimated_count, 0)
        self.assertLess(result.estimated_count, result.raw_count)

    def test_lora_acronym_requires_model_context(self):
        result = gate_sampled_count(
            raw_count=300,
            sample_texts=[
                "LoRa wireless sensor network for smart cities",
                "Long range LoRa propagation measurements",
                "LoRA adapters for LLM fine-tuning",
                "Low-Rank Adaptation of Large Language Models",
                "Parameter-efficient LoRA transformer adapters",
            ],
            anchor_text="LoRA Low-Rank Adaptation of Large Language Models",
            aliases=("low rank adaptation", "lora"),
            context_terms=("llm", "language model", "fine tuning", "transformer", "adapter"),
        )
        self.assertEqual((2, 3, 4), result.accepted_indices)
        self.assertEqual(180, result.estimated_count)

    def test_generic_language_model_adaptation_without_lora_is_rejected(self):
        result = gate_sampled_count(
            raw_count=3395,
            sample_texts=[
                "Feature Adaptation of Pre-Trained Language Models across Languages and Domains with Robust Self-Training",
                "Domain adaptation for pretrained language representations",
            ],
            anchor_text="LoRA Low-Rank Adaptation of Large Language Models",
            aliases=("low rank adaptation", "lora"),
            context_terms=("llm", "language model", "fine tuning", "transformer", "adapter"),
        )
        self.assertEqual((), result.accepted_indices)
        self.assertEqual(0, result.estimated_count)

    def test_generic_low_rank_adaptation_outside_model_context_is_rejected(self):
        result = gate_sampled_count(
            raw_count=200,
            sample_texts=[
                "Low rank adaptation for matrix approximation",
                "Low-rank adaptation in signal processing",
            ],
            anchor_text="LoRA Low-Rank Adaptation of Large Language Models",
            aliases=("low rank adaptation", "lora"),
            context_terms=("llm", "language model", "fine tuning", "transformer", "adapter"),
        )
        self.assertEqual(0, result.estimated_count)

    def test_single_sample_match_is_not_amplified(self):
        result = gate_sampled_count(
            raw_count=1000,
            sample_texts=[
                "LoRA adapters for LLM fine-tuning",
                "LoRa wireless network",
                "LoRa radio study",
                "Wireless long range telemetry",
                "LoRaWAN devices",
            ],
            anchor_text="LoRA Low-Rank Adaptation of Large Language Models",
            aliases=("low rank adaptation", "lora"),
            context_terms=("llm", "language model", "fine tuning", "transformer", "adapter"),
        )
        self.assertEqual(1, result.matched_sample_count)
        self.assertEqual(1, result.estimated_count)


if __name__ == "__main__":
    unittest.main()
