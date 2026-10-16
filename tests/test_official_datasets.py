from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from rideresolve.case_store import CaseStore
from rideresolve.integrity import compute_evidence_checksum
from rideresolve.models import ActionType, Evidence, SourceType
from rideresolve.policy import evaluate_case
from rideresolve.tool_service import (
    PolicyRulesRequest,
    ToolScope,
    ToolService,
    TripEvidenceRequest,
)


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_CASES_PATH = ROOT / "data" / "cases" / "official_cases.json"
SOURCE_DIR = ROOT / "data" / "official_sources"
MANIFEST_PATH = SOURCE_DIR / "source_manifest.json"


def replace_evidence_payload(item: Evidence, **updates: object) -> Evidence:
    payload = dict(item.payload)
    payload.update(updates)
    candidate = item.model_copy(update={"payload": payload, "checksum": ""})
    return candidate.model_copy(update={"checksum": compute_evidence_checksum(candidate)})


class OfficialDatasetIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = CaseStore.load_default()
        cls.dataset = json.loads(OFFICIAL_CASES_PATH.read_text(encoding="utf-8"))

    def evaluate(self, case_id: str):
        snapshot = self.store.get_snapshot(case_id, 1)
        return evaluate_case(
            snapshot,
            self.store.get_evidence(snapshot),
            self.store.get_policy(snapshot.policy_version),
        )

    def scope(self, case_id: str, actor_role: str = "EVIDENCE_COLLECTION") -> ToolScope:
        snapshot = self.store.get_snapshot(case_id, 1)
        return ToolScope(
            run_id=f"RUN-OFFICIAL-{case_id}",
            actor_role=actor_role,
            case_id=case_id,
            case_version=1,
            policy_version=snapshot.policy_version,
        )

    def test_official_source_manifest_hashes_match_archived_files(self) -> None:
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["source_kind"], "OFFICIAL_HACKATHON_SAMPLE_DATASET")
        self.assertEqual(
            manifest["precedence"],
            "OFFICIAL_VALUES_OVERRIDE_CONFLICTING_MOCK_VALUES",
        )
        self.assertEqual(len(manifest["files"]), 4)
        for entry in manifest["files"]:
            source = SOURCE_DIR / entry["name"]
            self.assertTrue(source.is_file(), entry["name"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), entry["sha256"])

    def test_store_merges_official_cases_without_removing_legacy_mock(self) -> None:
        self.assertEqual(
            self.store.dataset_id,
            "RIDERESOLVE_MERGED_MOCK_AND_OFFICIAL_SAMPLES_V1",
        )
        self.assertEqual(self.store.get_snapshot("DISP-001", 1).policy_version, "RYDE_POLICY_V2_1")
        self.assertEqual(self.store.get_snapshot("DISP-003", 1).dispute_type.value, "FARE_DISPUTE")
        self.assertEqual(self.store.get_snapshot("CASE-RD-001", 2).policy_version, "DEMO_POLICY_V1")

    def test_official_expected_results_are_reproduced_by_policy_code(self) -> None:
        for expected in self.dataset["expected_results"]:
            with self.subTest(case_id=expected["case_id"]):
                result = self.evaluate(expected["case_id"])
                self.assertEqual(result.business_status.value, expected["business_status"])
                self.assertEqual(list(result.matched_rule_ids), expected["matched_rule_ids"])
                self.assertEqual(result.allowed_action.model_dump(mode="json"), expected["action"])

    def test_official_route_values_override_old_mock_business_assumptions(self) -> None:
        result = self.evaluate("DISP-001")
        self.assertEqual(result.matched_rule_ids, ("RD-104",))
        self.assertEqual(result.allowed_action.type, ActionType.REFUND_DISPUTED_FEE_PARTIAL)
        self.assertEqual(result.allowed_action.fee_item, "excess_distance_fare")
        self.assertEqual(result.allowed_action.amount_cents, 344)
        self.assertEqual(result.metrics["deviation_m"], 4300.0)

    def test_official_summary_tools_preserve_decision_material_fields(self) -> None:
        service = ToolService(self.store)
        result = service.get_trip_evidence(
            self.scope("DISP-001"),
            TripEvidenceRequest(
                evidence_types=[
                    SourceType.PLATFORM_GPS,
                    SourceType.ROUTE_BASELINE,
                    SourceType.FARE_LEDGER,
                ],
                detail="SUMMARY",
            ),
        )
        by_type = {item["source_type"]: item for item in result["evidence"]}
        self.assertEqual(
            by_type["PLATFORM_GPS"]["payload"]["reported_actual_distance_m"],
            24800,
        )
        self.assertEqual(by_type["ROUTE_BASELINE"]["payload"]["baseline_distance_m"], 20500)
        self.assertTrue(by_type["FARE_LEDGER"]["checksum_verified"])
        self.assertEqual(result["gps_aggregate"]["coverage_percent"], 100.0)
        self.assertEqual(result["gps_aggregate"]["actual_distance_m"], 24800.0)
        self.assertEqual(result["gps_aggregate"]["unique_sample_count"], 16)
        self.assertFalse(result["gps_aggregate"]["conflict"])

    def test_official_policy_tool_exposes_versioned_precedents(self) -> None:
        service = ToolService(self.store)
        result = service.get_policy_rules(
            self.scope("DISP-001", "POLICY_PRECEDENT"),
            PolicyRulesRequest(),
        )
        self.assertEqual(result["policy_version"], "RYDE_POLICY_V2_1")
        self.assertEqual(len(result["rules"]), 6)
        self.assertEqual(len(result["policy_precedents"]), 3)
        self.assertEqual(result["policy_precedents"][0]["authority"], "ADVISORY_ONLY")

    def test_route_notification_changes_official_outcome_to_no_action(self) -> None:
        snapshot = self.store.get_snapshot("DISP-001", 1)
        evidence = self.store.get_evidence(snapshot)
        changed = [
            replace_evidence_payload(item, route_notification_sent=True)
            if item.source_type == SourceType.AUTHENTICATED_CHAT
            else item
            for item in evidence
        ]
        result = evaluate_case(snapshot, changed, self.store.get_policy(snapshot.policy_version))
        self.assertEqual(result.matched_rule_ids, ("RD-103",))
        self.assertEqual(result.allowed_action.type, ActionType.NO_ACTION)

    def test_no_show_requires_both_chat_and_phone_contact(self) -> None:
        snapshot = self.store.get_snapshot("DISP-002", 1)
        evidence = self.store.get_evidence(snapshot)
        changed = []
        for item in evidence:
            if item.source_type == SourceType.CONTACT_LOG:
                attempts = [
                    attempt
                    for attempt in item.payload["attempts"]
                    if attempt["channel"] != "PHONE"
                ]
                item = replace_evidence_payload(item, attempts=attempts)
            changed.append(item)
        result = evaluate_case(snapshot, changed, self.store.get_policy(snapshot.policy_version))
        self.assertEqual(result.matched_rule_ids, ("NS-105",))
        self.assertEqual(result.allowed_action.type, ActionType.REFUND_DISPUTED_FEE_FULL)
        self.assertEqual(result.allowed_action.amount_cents, 500)

    def test_fare_notification_changes_official_outcome_to_no_action(self) -> None:
        snapshot = self.store.get_snapshot("DISP-003", 1)
        evidence = self.store.get_evidence(snapshot)
        changed = [
            replace_evidence_payload(item, rider_notified=True)
            if item.source_type == SourceType.NOTIFICATION_LOG
            else item
            for item in evidence
        ]
        result = evaluate_case(snapshot, changed, self.store.get_policy(snapshot.policy_version))
        self.assertEqual(result.matched_rule_ids, ("FD-102",))
        self.assertEqual(result.allowed_action.type, ActionType.NO_ACTION)


if __name__ == "__main__":
    unittest.main()
