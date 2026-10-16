from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADP_API_DIRECTORY = ROOT / "api" / "adp"

EXPECTED_PATHS = {
    "evidence": {
        "/tools/get_case_snapshot",
        "/tools/get_trip_evidence",
        "/tools/get_policy_rules",
    },
    "rider": {"/tools/get_trip_evidence"},
    "driver": {"/tools/get_trip_evidence"},
    "policy": {"/tools/get_policy_rules", "/tools/search_precedents"},
    "gate": {
        "/tools/get_deterministic_evaluation",
        "/tools/validate_recommendation",
    },
}


class AdpRoleOpenApiTests(unittest.TestCase):
    def load(self, role: str) -> dict:
        path = ADP_API_DIRECTORY / f"rideresolve-{role}-tools.openapi.json"
        return json.loads(path.read_text(encoding="utf-8"))

    def test_role_documents_use_v040_live_server_and_least_privilege_paths(self) -> None:
        for role, expected_paths in EXPECTED_PATHS.items():
            with self.subTest(role=role):
                document = self.load(role)
                self.assertEqual(document["info"]["version"], "0.5.0")
                self.assertEqual(
                    document["servers"][0]["url"],
                    "https://rideresolve-gate-a-probe-325140-12-1501522460.sh.run.tcloudbase.com",
                )
                self.assertEqual(set(document["paths"]), expected_paths)
                self.assertEqual(
                    document["components"]["securitySchemes"]["RunToken"]["name"],
                    "X-RideResolve-Run-Token",
                )
                for path_item in document["paths"].values():
                    self.assertEqual(path_item["post"]["security"], [{"RunToken": []}])

    def test_official_evidence_types_are_available_to_evidence_and_advocates(self) -> None:
        for role in ("evidence", "rider", "driver"):
            with self.subTest(role=role):
                document = self.load(role)
                evidence_types = document["paths"]["/tools/get_trip_evidence"]["post"][
                    "requestBody"
                ]["content"]["application/json"]["schema"]["properties"][
                    "evidence_types"
                ]["items"]["enum"]
                self.assertIn("SURGE_PRICING_LOG", evidence_types)
                self.assertIn("NOTIFICATION_LOG", evidence_types)

    def test_gate_document_is_workflow_owned_not_judge_agent_owned(self) -> None:
        gate = self.load("gate")
        self.assertIn("Do not attach", gate["info"]["description"])
        self.assertFalse((ADP_API_DIRECTORY / "rideresolve-judge-tools.openapi.json").exists())


if __name__ == "__main__":
    unittest.main()
