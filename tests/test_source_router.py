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

    def test_b033_source_executability_is_not_policy_enablement(self):
        for direction, expected_profile, expected_ready, expected_blocked in (
            ("AI agents", "software_ai", {"github", "openalex"}, {"huggingface", "epo_ops"}),
            ("neuromorphic computing", "hardware_semiconductor", {"openalex", "github"}, {"epo_ops", "huggingface"}),
            ("solid-state batteries", "materials_energy", {"openalex"}, {"epo_ops"}),
        ):
            with self.subTest(direction=direction):
                route = self.router.route(direction)
                self.assertEqual(expected_profile, route.profile)
                self.assertEqual(expected_ready, {p.provider for p in route.collectable_providers})
                self.assertEqual(expected_blocked, {p.provider for p in route.blocked_providers})
                self.assertTrue({p.provider for p in route.collectable_providers}.issubset(
                    {p.provider for p in route.enabled_providers}
                ))
                self.assertEqual("credentials_missing",
                                 next(p.execution_status for p in route.providers if p.provider == "epo_ops"))
                self.assertEqual("adapter_missing",
                                 next(p.execution_status for p in route.providers if p.provider == "huggingface"))

    def test_provider_routing_does_not_claim_patent_or_hf_adapter_is_installed(self):
        software = self.router.route("AI agents")
        self.assertEqual(("github", "openalex"),
                         tuple(provider.provider for provider in software.collectable_providers))
        batteries = self.router.route("solid-state batteries")
        self.assertNotIn("github", {p.provider for p in batteries.enabled_providers})
        self.assertNotIn("huggingface", {p.provider for p in batteries.collectable_providers})

    def test_russian_direction_examples_and_manual_override(self):
        self.assertEqual("hardware_semiconductor",
                         self.router.route("нейроморфные процессоры").profile)
        self.assertEqual("materials_energy",
                         self.router.route("твердотельные аккумуляторы").profile)
        override = self.router.route("AI agents", profile_override="materials_energy")
        self.assertEqual({"openalex"}, {p.provider for p in override.collectable_providers})

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
