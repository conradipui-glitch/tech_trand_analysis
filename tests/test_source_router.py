import unittest
from pathlib import Path

from tech_trend_analysis.source_router import SourceRouter, classify_direction

ROOT = Path(__file__).resolve().parents[1]


class SourceRouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.router = SourceRouter.from_yaml(ROOT / "config" / "sources.yaml")

    def test_ai_agents_routes_to_software_ai(self):
        route = self.router.route("AI agents")
        self.assertEqual("software_ai", route.profile)
        enabled = {provider.provider: provider for provider in route.enabled_providers}
        self.assertGreater(
            enabled["github"].collection_priority,
            enabled["openalex"].collection_priority,
        )
        self.assertIn("huggingface", enabled)

    def test_russian_ai_direction_is_detected_as_ai(self):
        profile, confidence, matched = classify_direction("технологии в ИИ")
        self.assertEqual("software_ai", profile)
        self.assertGreater(confidence, 0.5)
        self.assertIn("ии", matched)

    def test_neuromorphic_routes_to_hardware_profile(self):
        route = self.router.route("neuromorphic computing")
        self.assertEqual("hardware_semiconductor", route.profile)
        enabled = {provider.provider for provider in route.enabled_providers}
        self.assertTrue({"epo_ops", "openalex", "github"}.issubset(enabled))

    def test_solid_state_batteries_disable_software_sources(self):
        route = self.router.route("solid-state batteries")
        self.assertEqual("materials_energy", route.profile)
        all_routes = {provider.provider: provider for provider in route.providers}
        self.assertTrue(all_routes["epo_ops"].enabled)
        self.assertTrue(all_routes["openalex"].enabled)
        self.assertFalse(all_routes["github"].enabled)
        self.assertFalse(all_routes["huggingface"].enabled)

    def test_unknown_direction_falls_back_to_mixed(self):
        route = self.router.route("frontier systems for future infrastructure")
        self.assertEqual("mixed", route.profile)
        self.assertLess(route.confidence, 0.5)

    def test_profile_override_is_deterministic(self):
        route = self.router.route(
            "ambiguous technology",
            profile_override="materials_energy",
        )
        self.assertEqual("materials_energy", route.profile)
        self.assertEqual(1.0, route.confidence)


if __name__ == "__main__":
    unittest.main()
