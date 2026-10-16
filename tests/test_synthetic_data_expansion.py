from __future__ import annotations

import json
import unittest
from pathlib import Path

from rideresolve.case_store import CaseStore
from rideresolve.models import CaseSnapshot, DisputeType, Evidence
from rideresolve.policy import evaluate_case, load_policy


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "cases" / "tool_cases.json"
POLICY_PATH = ROOT / "data" / "policies" / "DEMO_POLICY_V1.json"


class SyntheticDataExpansionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        cls.cases = [CaseSnapshot.model_validate(item) for item in cls.raw["cases"]]
        cls.evidence = [Evidence.model_validate(item) for item in cls.raw["evidence"]]
        cls.policy = load_policy(POLICY_PATH)

    def test_dataset_is_synthetic_integrity_checked_and_target_sized(self):
        store = CaseStore.load_default()
        unique_cases = {(case.case_id, case.dispute_type) for case in self.cases}

        self.assertTrue(store.synthetic)
        self.assertEqual(16, len(unique_cases))
        self.assertEqual(
            8,
            sum(dispute_type == DisputeType.ROUTE_DEVIATION for _, dispute_type in unique_cases),
        )
        self.assertEqual(
            8,
            sum(dispute_type == DisputeType.NO_SHOW for _, dispute_type in unique_cases),
        )

    def test_persisted_cases_cover_every_policy_rule(self):
        covered_rules: set[str] = set()
        for snapshot in self.cases:
            evaluation = evaluate_case(snapshot, self.evidence, self.policy)
            covered_rules.update(evaluation.matched_rule_ids)

        policy_rules = {rule["rule_id"] for rule in self.policy.rules}
        self.assertEqual(policy_rules, covered_rules)

    def test_timestamps_amounts_and_claims_are_not_binary_templates(self):
        unique_case_versions = {
            case.case_id: case
            for case in sorted(self.cases, key=lambda item: item.case_version)
        }

        self.assertGreaterEqual(
            len({case.trip_started_at.date() for case in unique_case_versions.values()}),
            10,
        )
        self.assertGreaterEqual(
            len({case.disputed_amount_cents for case in unique_case_versions.values()}),
            10,
        )
        self.assertGreaterEqual(
            len({case.claim_text for case in unique_case_versions.values()}),
            10,
        )


if __name__ == "__main__":
    unittest.main()
