import copy
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas"
EXAMPLES = SCHEMAS / "examples"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observation_schema = load_json(SCHEMAS / "observation.schema.json")
        cls.result_schema = load_json(SCHEMAS / "trend-result.schema.json")
        Draft202012Validator.check_schema(cls.observation_schema)
        Draft202012Validator.check_schema(cls.result_schema)
        cls.observation_validator = Draft202012Validator(
            cls.observation_schema, format_checker=FormatChecker()
        )
        cls.result_validator = Draft202012Validator(
            cls.result_schema, format_checker=FormatChecker()
        )

    def assert_valid(self, validator, payload):
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        self.assertEqual([], [error.message for error in errors])

    def test_github_observation_fixture(self):
        payload = load_json(EXAMPLES / "observation.github.json")
        self.assert_valid(self.observation_validator, payload)

    def test_patent_observation_fixture(self):
        payload = load_json(EXAMPLES / "observation.patent.synthetic.json")
        self.assert_valid(self.observation_validator, payload)

    def test_new_provider_does_not_require_schema_change(self):
        payload = load_json(EXAMPLES / "observation.github.json")
        payload = copy.deepcopy(payload)
        payload["provider"] = "future_provider"
        payload["artifact_kind"] = "prototype_registry_entry"
        payload["external_id"] = "future:1"
        payload["observation_id"] = "future_provider:1"
        self.assert_valid(self.observation_validator, payload)

    def test_evidence_taxonomy_is_stable(self):
        payload = load_json(EXAMPLES / "observation.github.json")
        payload = copy.deepcopy(payload)
        payload["evidence_type"] = "random_provider_specific_type"
        errors = list(self.observation_validator.iter_errors(payload))
        self.assertTrue(errors)

    def test_trend_result_fixture(self):
        payload = load_json(EXAMPLES / "trend-result.example.json")
        self.assert_valid(self.result_validator, payload)


if __name__ == "__main__":
    unittest.main()
