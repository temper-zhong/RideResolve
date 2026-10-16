from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "adp" / "accuracy_first_manifest.json"
PROMPT_DIR = ROOT / "docs" / "adp" / "prompts" / "accuracy_first"


class AccuracyFirstWorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_official_data_and_deterministic_policy_are_authoritative(self) -> None:
        self.assertEqual(
            "OFFICIAL_OVER_LEGACY_MOCK",
            self.manifest["data_precedence"],
        )
        self.assertTrue(
            self.manifest["invariants"]["deterministic_policy_is_authoritative"]
        )
        self.assertEqual(
            "WF.final_result",
            self.manifest["invariants"]["end_output_source"],
        )

    def test_five_agents_remain_and_judge_has_no_attached_tools(self) -> None:
        agents = [
            node
            for node in self.manifest["main_sequence"]
            if node["type"] == "AGENT"
        ]
        self.assertEqual(5, len(agents))
        judge = next(node for node in agents if node["agent_ref"] == "Judge")
        self.assertEqual([], judge["tools"])

    def test_all_agent_execution_is_serial(self) -> None:
        self.assertEqual(
            "STRICTLY_SEQUENTIAL",
            self.manifest["invariants"]["agent_execution"],
        )
        self.assertNotIn("PARALLEL", json.dumps(self.manifest))
        self.assertEqual(
            "DECISION_FACTS",
            self.manifest["tool_defaults"]["trip_evidence"]["detail"],
        )

    def test_external_user_query_is_resolved_without_guessing(self) -> None:
        self.assertEqual("SYS.UserQuery", self.manifest["external_input"])
        self.assertFalse(self.manifest["invariants"]["description_only_case_guessing"])
        nodes = {node["id"]: node for node in self.manifest["main_sequence"]}
        self.assertEqual(
            "SYS.UserQuery",
            nodes["resolve_case_context"]["request"]["user_query"],
        )
        self.assertEqual(
            "set_clarification_result",
            nodes["require_matched_case"]["false_branch"],
        )

    def test_gate_calls_are_workflow_owned_and_final(self) -> None:
        nodes = {
            node["id"]: node
            for node in self.manifest["main_sequence"]
        }
        for node_id in ("get_deterministic_evaluation", "validate_recommendation"):
            self.assertEqual("JUDGE", nodes[node_id]["credential_role"])
            self.assertFalse(nodes[node_id]["attach_to_agent"])
        self.assertEqual(
            {"result": "WF.final_result"},
            nodes["end"]["output"],
        )

    def test_exactly_one_end_and_shared_failure_result(self) -> None:
        serialized = json.dumps(self.manifest)
        end_nodes = [
            node
            for section in ("main_sequence", "clarification_branch", "failure_branch")
            for node in self.manifest[section]
            if node["type"] == "END"
        ]
        self.assertEqual(1, len(end_nodes))
        self.assertIn("TECHNICAL_FAILURE", serialized)

    def test_deployment_prompts_do_not_embed_demo_policy(self) -> None:
        for path in PROMPT_DIR.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("Embedded DEMO_POLICY_V1", text, path.name)
            self.assertNotIn("Use only the supplied DEMO policy", text, path.name)
        judge = (PROMPT_DIR / "judge.md").read_text(encoding="utf-8")
        self.assertIn("Copy recommended_case_status exactly", judge)
        self.assertIn("Official data", judge)


if __name__ == "__main__":
    unittest.main()
