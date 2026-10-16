from __future__ import annotations

import unittest
import json
from pathlib import Path

from rideresolve.session_openapi import (
    ROLE_PATHS,
    build_intake_openapi_schema,
    build_session_role_documents,
)


class SessionOpenApiTests(unittest.TestCase):
    def test_intake_uses_user_query_and_returns_run_context(self) -> None:
        document = build_intake_openapi_schema("https://example.invalid")
        operation = document["paths"]["/tools/resolve_case_context"]["post"]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(["user_query"], schema["required"])
        self.assertEqual({"user_query"}, set(schema["properties"]))
        result = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]["properties"]["result"]
        self.assertIn("run_context", result["properties"])
        self.assertEqual([{"IntakeToken": []}], operation["security"])

    def test_all_role_operations_require_signed_context(self) -> None:
        documents = build_session_role_documents("https://example.invalid")
        self.assertEqual(set(ROLE_PATHS), set(documents))
        for role, document in documents.items():
            self.assertEqual(set(ROLE_PATHS[role]), set(document["paths"]))
            for item in document["paths"].values():
                operation = item["post"]
                schema = operation["requestBody"]["content"]["application/json"][
                    "schema"
                ]
                self.assertIn("run_context", schema["required"])
                self.assertIn("run_context", schema["properties"])
                self.assertEqual([{"ConnectorToken": []}], operation["security"])

    def test_gate_transports_recommendation_as_json_string(self) -> None:
        gate = build_session_role_documents("https://example.invalid")["gate"]
        self.assertEqual(
            "RideResolve Deterministic Gate Tools v0.6 ADP Safe",
            gate["info"]["title"],
        )
        schema = gate["paths"]["/tools/validate_recommendation"]["post"][
            "requestBody"
        ]["content"]["application/json"]["schema"]
        recommendation = schema["properties"]["recommendation"]
        self.assertEqual("string", recommendation["type"])
        self.assertEqual(2, recommendation["minLength"])

    def test_checked_in_documents_match_builders(self) -> None:
        root = Path(__file__).resolve().parents[1]
        output = root / "api" / "adp" / "v0_6"
        intake = json.loads(
            (output / "rideresolve-intake-tools.openapi.json").read_text(encoding="utf-8")
        )
        server_url = intake["servers"][0]["url"]
        self.assertEqual(build_intake_openapi_schema(server_url), intake)
        role_documents = build_session_role_documents(server_url)
        for role, expected in role_documents.items():
            persisted = json.loads(
                (output / f"rideresolve-{role}-tools.openapi.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(expected, persisted)


if __name__ == "__main__":
    unittest.main()
