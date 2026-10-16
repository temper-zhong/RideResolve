from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from rideresolve.case_store import CaseStore, merge_dataset_records
from rideresolve.integrity import evidence_checksum_is_valid
from rideresolve.intake import IntakeRequest, OfficialCaseResolver
from rideresolve.models import CaseSnapshot, Evidence
from rideresolve.policy import evaluate_case


ROOT = Path(__file__).resolve().parents[1]
DEMO_PATH = ROOT / "data" / "cases" / "synthetic_demo_cases.json"
OFFICIAL_PATH = ROOT / "data" / "cases" / "official_cases.json"


class PublicDemoCaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = CaseStore.load_default()
        cls.resolver = OfficialCaseResolver(cls.store)
        cls.dataset = json.loads(DEMO_PATH.read_text(encoding="utf-8"))

    def test_official_and_synthetic_demo_sets_are_separate(self) -> None:
        official = {item.case_id for item in self.store.list_official_snapshots()}
        demos = {item.case_id for item in self.store.list_demo_snapshots()}
        self.assertEqual({"DISP-001", "DISP-002", "DISP-003"}, official)
        self.assertEqual(9, len(demos))
        self.assertTrue(all(case_id.startswith("DEMO-") for case_id in demos))
        self.assertTrue(official.isdisjoint(demos))

    def test_demo_dataset_has_prominent_synthetic_markers(self) -> None:
        self.assertTrue(self.dataset["synthetic"])
        self.assertEqual(
            "SYNTHETIC_PUBLIC_DEMO_DATASET",
            self.dataset["source_kind"],
        )
        self.assertIn("fictional", self.dataset["disclaimer"].lower())
        for item in self.dataset["cases"]:
            self.assertTrue(item["claim_text"].startswith("[SYNTHETIC DEMO]"))
        for item in self.dataset["evidence"]:
            self.assertIn("not an official", item["provenance_reason"].lower())
            self.assertTrue(evidence_checksum_is_valid(Evidence.model_validate(item)))

    def test_all_demo_expected_results_are_reproduced(self) -> None:
        expected_by_case = {
            item["case_id"]: item for item in self.dataset["expected_results"]
        }
        for snapshot in self.store.list_demo_snapshots():
            with self.subTest(case_id=snapshot.case_id):
                result = evaluate_case(
                    snapshot,
                    self.store.get_evidence(snapshot),
                    self.store.get_policy(snapshot.policy_version),
                )
                expected = expected_by_case[snapshot.case_id]
                self.assertEqual(expected["business_status"], result.business_status.value)
                self.assertEqual(expected["matched_rule_ids"], list(result.matched_rule_ids))
                self.assertEqual(
                    expected["action"],
                    result.allowed_action.model_dump(mode="json")
                    if result.allowed_action is not None
                    else None,
                )

    def test_demo_case_and_trip_references_are_resolvable_and_labeled(self) -> None:
        by_case = self.resolver.resolve(
            IntakeRequest(user_query="Please review synthetic demo DEMO-202.")
        )
        self.assertEqual("MATCHED", by_case.status)
        self.assertEqual("DEMO-202", by_case.snapshot.case_id)
        self.assertEqual("SYNTHETIC_DEMO", by_case.case_origin)

        by_trip = self.resolver.resolve(
            IntakeRequest(user_query="Please review trip TRIP-2026-20302.")
        )
        self.assertEqual("MATCHED", by_trip.status)
        self.assertEqual("DEMO-302", by_trip.snapshot.case_id)
        self.assertEqual("SYNTHETIC_DEMO", by_trip.case_origin)

    def test_official_records_override_synthetic_identity_conflicts(self) -> None:
        official = json.loads(OFFICIAL_PATH.read_text(encoding="utf-8"))
        synthetic_conflict = {
            "cases": [copy.deepcopy(official["cases"][0])],
            "evidence": [
                copy.deepcopy(item)
                for item in official["evidence"]
                if item["evidence_id"] in official["cases"][0]["evidence_refs"]
            ],
        }
        synthetic_conflict["cases"][0]["claim_text"] = "synthetic conflicting value"
        merged_cases, merged_evidence = merge_dataset_records(
            [synthetic_conflict, official]
        )
        merged = {
            (item["case_id"], item["case_version"]): item for item in merged_cases
        }
        self.assertEqual(
            official["cases"][0]["claim_text"],
            merged[("DISP-001", 1)]["claim_text"],
        )
        official_evidence = {item["evidence_id"]: item for item in official["evidence"]}
        merged_evidence_by_id = {item["evidence_id"]: item for item in merged_evidence}
        first_id = official["cases"][0]["evidence_refs"][0]
        self.assertEqual(official_evidence[first_id], merged_evidence_by_id[first_id])
        CaseSnapshot.model_validate(merged[("DISP-001", 1)])


if __name__ == "__main__":
    unittest.main()
