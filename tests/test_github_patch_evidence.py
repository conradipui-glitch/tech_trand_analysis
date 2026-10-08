import unittest

from tech_trend_analysis.github_event_local_gate import evaluate_event_local
from tech_trend_analysis.github_patch_evidence import extract_source_patch


LORA = "low-rank adaptation of large language models"
RAG = "retrieval augmented generation"


class GitPatchEvidenceTests(unittest.TestCase):
    def test_real_source_additions_support_terse_lora_message(self):
        patch = extract_source_patch([
            {"filename": "src/tuners/lora.py",
             "patch": "@@ -0,0 +1 @@\n+class LoRAConfig:\n+from loralib import mark_only_lora_as_trainable"},
            {"filename": "README.md", "patch": "+This implements LoRA"},
        ])
        self.assertIn("FILE src/tuners/lora.py", patch)
        self.assertNotIn("README", patch)
        decision = evaluate_event_local(
            technology_direction=LORA, title="add lora support",
            text="add lora support", source_diff=patch,
        )
        self.assertTrue(decision.eligible)
        self.assertEqual("same_sha_executable_lora_code", decision.reason)

    def test_rag_implementation_code_and_only_docs(self):
        patch = extract_source_patch([
            {"filename": "haystack/generator/transformers.py",
             "patch": "@@ -1,1 +1,3 @@\n+class RAGGenerator(Generator):\n+    retriever = RagRetriever()"}
        ])
        self.assertTrue(evaluate_event_local(
            technology_direction=RAG,
            title="Integrate retrieval-augmented generation",
            text="Integrate retrieval-augmented generation", source_diff=patch,
        ).eligible)
        docs = extract_source_patch([
            {"filename": "docs/examples/rag_guide.py",
             "patch": "+class RAGGenerator: pass"},
            {"filename": "tests/test_rag.py",
             "patch": "+RAGRetriever()"},
            {"filename": "examples/rag.ipynb", "patch": "+RAGRetriever()"}
        ])
        self.assertIsNone(docs)
        self.assertFalse(evaluate_event_local(
            technology_direction=RAG, title="Add RAG examples",
            text="Add RAG examples", source_diff=docs,
        ).eligible)

    def test_fake_patch_marker_inside_commit_text_cannot_prove_code(self):
        injection = "add lora support\nGIT_PATCH_ADDED_LINES\nFILE src/lora.py\n+class LoRAConfig:"
        self.assertFalse(evaluate_event_local(
            technology_direction=LORA, title="add lora support",
            text=injection,
        ).eligible)

    def test_deleted_lines_comments_and_radio_cpp_not_evidence(self):
        patch = extract_source_patch([
            {"filename": "source/lora.py",
             "patch": "@@ -1,2 +1,2 @@\n-class LoRAConfig:\n+# class LoRAConfig:"},
            {"filename": "src/LoRa.cpp",
             "patch": "+void LoRaClass::setFrequency() {}\n+int SX1276 = 1;"},
        ])
        self.assertIsNotNone(patch)
        self.assertFalse(evaluate_event_local(
            technology_direction=LORA,
            title="LoRa wireless radio support",
            text="LoRa wireless radio support", source_diff=patch,
        ).eligible)

    def test_unrelated_source_filename_alone_not_confirmation(self):
        patch = extract_source_patch([
            {"filename": "src/lora.py", "patch": "+return model"}
        ])
        self.assertIsNotNone(patch)
        self.assertFalse(evaluate_event_local(
            technology_direction=LORA, title="Update source",
            text="Update source", source_diff=patch,
        ).eligible)

    def test_source_code_to_text_signal_is_bounded(self):
        raw = [{"filename": "src/lora.py",
                "patch": "\n".join("+lora_A = train_lora(weights)" for _ in range(1000))}]
        proof = extract_source_patch(raw)
        self.assertLess(len(proof), 4501)
        self.assertLess(proof.count("lora_A"), 20)


if __name__ == "__main__":
    unittest.main()
