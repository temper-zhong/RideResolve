from __future__ import annotations

import json
import unittest
from pathlib import Path

from rideresolve.run_registry import AgentRole
from rideresolve.tool_api import (
    _CASE_PATH,
    _EVIDENCE_PATH,
    _EVALUATION_PATH,
    _POLICY_PATH,
    _PRECEDENT_PATH,
    _ROLE_PATH_PERMISSIONS,
    _VALIDATION_PATH,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "docs" / "adp" / "workflow_first_manifest.json"
PROMPT_DIR = ROOT / "docs" / "adp" / "prompts"


class WorkflowFirstContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_every_agent_has_no_bound_tools(self) -> None:
        bindings = self.manifest["agent_tool_bindings"]
        self.assertEqual(5, len(bindings))
        self.assertTrue(all(tools == [] for tools in bindings.values()))
        agent_nodes = [
            node for node in self.manifest["nodes"] if node["type"] == "AGENT"
        ]
        self.assertEqual(5, len(agent_nodes))
        self.assertTrue(all(node["tools"] == [] for node in agent_nodes))

    def test_tool_calls_are_explicit_and_role_scoped(self) -> None:
        tool_nodes = [
            node for node in self.manifest["nodes"] if node["type"] == "TOOL"
        ]
        self.assertEqual(7, len(tool_nodes))
        self.assertEqual(
            [
                "get_case_snapshot",
                "get_trip_evidence",
                "get_policy_rules",
                "get_trip_evidence",
                "get_trip_evidence",
                "get_policy_rules",
                "search_precedents",
            ],
            [node["operation"] for node in tool_nodes],
        )
        self.assertTrue(all(node.get("credential_role") for node in tool_nodes))

    def test_server_permissions_match_workflow_nodes(self) -> None:
        self.assertEqual(
            frozenset({_CASE_PATH, _EVIDENCE_PATH, _POLICY_PATH}),
            _ROLE_PATH_PERMISSIONS[AgentRole.EVIDENCE_COLLECTION],
        )
        self.assertEqual(
            frozenset({_EVIDENCE_PATH}),
            _ROLE_PATH_PERMISSIONS[AgentRole.RIDER_ADVOCATE],
        )
        self.assertEqual(
            frozenset({_EVIDENCE_PATH}),
            _ROLE_PATH_PERMISSIONS[AgentRole.DRIVER_ADVOCATE],
        )
        self.assertEqual(
            frozenset({_POLICY_PATH, _PRECEDENT_PATH}),
            _ROLE_PATH_PERMISSIONS[AgentRole.POLICY_PRECEDENT],
        )
        self.assertEqual(
            frozenset({_EVALUATION_PATH, _VALIDATION_PATH}),
            _ROLE_PATH_PERMISSIONS[AgentRole.JUDGE],
        )

    def test_graph_is_one_closed_linear_chain(self) -> None:
        nodes = self.manifest["nodes"]
        by_id = {node["id"]: node for node in nodes}
        self.assertEqual(len(nodes), len(by_id))
        current = "start"
        visited: list[str] = []
        while current != "end":
            self.assertNotIn(current, visited)
            visited.append(current)
            current = by_id[current]["next"]
        visited.append("end")
        self.assertEqual(set(by_id), set(visited))

    def test_prompts_enforce_workflow_owned_tools(self) -> None:
        for path in PROMPT_DIR.glob("*.md"):
            text = path.read_text(encoding="utf-8")
            self.assertIn("Do not call tools", text, path.name)
            self.assertNotIn("Make exactly three successful native tool calls", text, path.name)
            self.assertNotIn("Make exactly two successful native tool calls", text, path.name)
            self.assertNotIn("Call get_trip_evidence exactly once", text, path.name)


if __name__ == "__main__":
    unittest.main()
