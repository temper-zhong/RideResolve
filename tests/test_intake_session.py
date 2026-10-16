from __future__ import annotations

import json
import base64
import hashlib
import tempfile
import threading
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from rideresolve.case_store import CaseStore
from rideresolve.intake import IntakeRequest, IntakeService, OfficialCaseResolver
from rideresolve.run_registry import AgentRole, RunRegistry
from rideresolve.session_auth import (
    ConnectorCredentialExpiredError,
    ConnectorCredentialSet,
    RunContextError,
    RunContextSigner,
)
from rideresolve.tool_api import create_http_server
from rideresolve.tool_audit import JsonlAuditLogger
from rideresolve.tool_service import ToolService


class OfficialCaseResolverTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = CaseStore.load_default()
        cls.resolver = OfficialCaseResolver(cls.store)

    def test_exact_case_reference_in_natural_language_matches_official_case(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(user_query="Please review my longer-route complaint, case DISP-001.")
        )
        self.assertEqual("MATCHED", result.status)
        self.assertEqual("DISP-001", result.snapshot.case_id)

    def test_exact_trip_reference_matches_official_case(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(user_query="My trip TRIP-2026-10023 was charged above the quote.")
        )
        self.assertEqual("MATCHED", result.status)
        self.assertEqual("DISP-003", result.snapshot.case_id)

    def test_description_without_official_identifier_is_never_guessed(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(
                user_query="The driver took a longer route and I want the extra fare refunded."
            )
        )
        self.assertEqual("NEEDS_CLARIFICATION", result.status)
        self.assertIsNone(result.snapshot)

    def test_legacy_mock_case_is_not_resolved_by_official_intake(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(user_query="Please check CASE-RD-TOOL-001 for me.")
        )
        self.assertEqual("NEEDS_CLARIFICATION", result.status)
        self.assertIsNone(result.snapshot)

    def test_unknown_official_reference_is_not_found(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(user_query="Please review DISP-999.")
        )
        self.assertEqual("NOT_FOUND", result.status)

    def test_conflicting_references_require_clarification(self) -> None:
        result = self.resolver.resolve(
            IntakeRequest(user_query="Compare DISP-001 and TRIP-2026-10023.")
        )
        self.assertEqual("NEEDS_CLARIFICATION", result.status)


class SessionSecurityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.current = datetime(2026, 10, 15, 2, 0, tzinfo=UTC)
        self.store = CaseStore.load_default()
        self.registry = RunRegistry(
            Path(self.temporary.name) / "registry.json",
            self.store,
            now=lambda: self.current,
        )
        self.signer = RunContextSigner(b"s" * 32, now=lambda: self.current)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_context_tampering_and_expiry_fail_closed(self) -> None:
        issued = self.registry.create_run("DISP-001", 1, ttl_seconds=60)
        value = self.signer.issue(issued)
        claims = self.signer.verify(value)
        self.assertEqual(issued.run_id, claims.run_id)
        with self.assertRaises(RunContextError):
            self.signer.verify(value[:-1] + ("A" if value[-1] != "A" else "B"))
        expired = RunContextSigner(
            b"s" * 32,
            now=lambda: self.current + timedelta(seconds=61),
        )
        with self.assertRaises(RunContextError):
            expired.verify(value)

    def test_connector_credentials_enforce_expiry(self) -> None:
        credentials = ConnectorCredentialSet.from_plaintext(
            intake_token="intake",
            role_tokens={role: f"token-{role.value}" for role in AgentRole},
            expires_at=self.current + timedelta(seconds=1),
            now=lambda: self.current + timedelta(seconds=2),
        )
        with self.assertRaises(ConnectorCredentialExpiredError):
            credentials.authorize_intake("intake")

    def test_hashed_bundle_authenticates_without_storing_raw_tokens(self) -> None:
        role_tokens = {role: f"bundle-{role.value}" for role in AgentRole}
        bundle = {
            "schema_version": 1,
            "expires_at": (self.current + timedelta(days=1)).isoformat(),
            "intake": {"token_hash": hashlib.sha256(b"intake").hexdigest()},
            "roles": {
                role.value: {
                    "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest()
                }
                for role, token in role_tokens.items()
            },
        }
        encoded = base64.b64encode(json.dumps(bundle).encode("utf-8")).decode("ascii")
        credentials = ConnectorCredentialSet.from_base64(
            encoded,
            now=lambda: self.current,
        )
        credentials.authorize_intake("intake")
        self.assertEqual(
            AgentRole.JUDGE,
            credentials.authorize_role(role_tokens[AgentRole.JUDGE]),
        )


class IntakeHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        # Production intake timestamps include microseconds. Keep them here so the
        # HTTP integration tests cover NumericDate's whole-second precision.
        cls.current = datetime(2026, 10, 15, 2, 0, 0, 423806, tzinfo=UTC)
        cls.service = ToolService.load_default()
        cls.registry = RunRegistry(
            cls.root / "registry.json",
            cls.service.store,
            now=lambda: cls.current,
        )
        cls.signer = RunContextSigner(b"c" * 32, now=lambda: cls.current)
        cls.intake_token = "intake-secret"
        cls.role_tokens = {role: f"session-{role.value}" for role in AgentRole}
        cls.credentials = ConnectorCredentialSet.from_plaintext(
            intake_token=cls.intake_token,
            role_tokens=cls.role_tokens,
            expires_at=datetime(2026, 11, 4, 15, 59, 59, tzinfo=UTC),
            now=lambda: cls.current,
        )
        cls.audit = JsonlAuditLogger(cls.root / "audit.jsonl")
        intake = IntakeService(
            OfficialCaseResolver(cls.service.store),
            cls.registry,
            cls.signer,
            max_requests_per_role=300,
        )
        cls.server = create_http_server(
            "127.0.0.1",
            0,
            registry=cls.registry,
            audit_logger=cls.audit,
            service=cls.service,
            connector_credentials=cls.credentials,
            run_context_signer=cls.signer,
            intake_service=intake,
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    @classmethod
    def post(cls, path: str, payload: dict, headers: dict[str, str]):
        request = Request(
            cls.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        return urlopen(request, timeout=5)

    def test_intake_creates_context_and_static_role_token_uses_it(self) -> None:
        private_phrase = "PRIVATE_QUERY_MUST_NOT_ENTER_AUDIT"
        with self.post(
            "/tools/resolve_case_context",
            {"user_query": f"{private_phrase}: please review DISP-002"},
            {"X-RideResolve-Intake-Token": self.intake_token},
        ) as response:
            intake_body = json.load(response)
        result = intake_body["result"]
        self.assertEqual("MATCHED", result["resolution_status"])
        self.assertEqual("DISP-002", result["case_id"])
        self.assertTrue(result["run_created"])
        self.assertEqual(
            423806,
            self.registry.get_manifest_scope(result["run_id"]).expires_at.microsecond,
        )

        with self.post(
            "/tools/get_trip_evidence",
            {
                "run_context": result["run_context"],
                "evidence_types": ["PLATFORM_GPS"],
                "detail": "DECISION_FACTS",
            },
            {"X-RideResolve-Run-Token": self.role_tokens[AgentRole.RIDER_ADVOCATE]},
        ) as response:
            evidence_body = json.load(response)
        self.assertEqual("DISP-002", evidence_body["result"]["case_id"])
        self.assertEqual("RIDER_ADVOCATE", evidence_body["result"]["tool_actor_role"])
        self.assertNotIn(private_phrase, (self.root / "audit.jsonl").read_text(encoding="utf-8"))

    def test_static_role_cannot_cross_permissions(self) -> None:
        with self.post(
            "/tools/resolve_case_context",
            {"user_query": "review DISP-001"},
            {"X-RideResolve-Intake-Token": self.intake_token},
        ) as response:
            context = json.load(response)["result"]["run_context"]
        with self.assertRaises(HTTPError) as caught:
            self.post(
                "/tools/get_policy_rules",
                {"run_context": context, "scope": "APPLICABLE_DISPUTE"},
                {"X-RideResolve-Run-Token": self.role_tokens[AgentRole.RIDER_ADVOCATE]},
            )
        self.assertEqual(403, caught.exception.code)

    def test_invalid_context_is_rejected(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            self.post(
                "/tools/get_trip_evidence",
                {
                    "run_context": "not-a-valid-context",
                    "evidence_types": ["FARE_LEDGER"],
                },
                {"X-RideResolve-Run-Token": self.role_tokens[AgentRole.RIDER_ADVOCATE]},
            )
        self.assertEqual(401, caught.exception.code)
        body = json.loads(caught.exception.read().decode("utf-8"))
        self.assertEqual("INVALID_RUN_CONTEXT", body["error"]["code"])

    def test_official_session_reaches_deterministic_validation(self) -> None:
        with self.post(
            "/tools/resolve_case_context",
            {"user_query": "The route was longer; please review DISP-001."},
            {"X-RideResolve-Intake-Token": self.intake_token},
        ) as response:
            session = json.load(response)["result"]
        with self.post(
            "/tools/get_deterministic_evaluation",
            {"run_context": session["run_context"], "scope": "LOCKED_RUN"},
            {"X-RideResolve-Run-Token": self.role_tokens[AgentRole.JUDGE]},
        ) as response:
            deterministic = json.load(response)["result"]
        evaluation = deterministic["evaluation"]
        self.assertEqual(["RD-104"], evaluation["matched_rule_ids"])
        self.assertEqual(344, evaluation["allowed_action"]["amount_cents"])
        recommendation = {
            "recommended_case_status": evaluation["business_status"],
            "recommended_action": evaluation["allowed_action"],
            "evidence_citations": deterministic["decision_evidence_ids"],
            "policy_citations": evaluation["matched_rule_ids"],
            "judge_confidence": {
                "score": 90,
                "label": "UNCALIBRATED_MODEL_SELF_ASSESSMENT",
                "rationale": "The authoritative fields were copied without modification.",
            },
            "reasoning_summary": "The deterministic result controls the recommendation.",
            "uncertainties": [],
            "rider_explanation": "The deterministic gate recommends the policy-authorized result.",
            "driver_explanation": "The deterministic gate recommends the policy-authorized result.",
        }
        with self.post(
            "/tools/validate_recommendation",
            {
                "run_context": session["run_context"],
                "run_id": session["run_id"],
                "recommendation": recommendation,
            },
            {"X-RideResolve-Run-Token": self.role_tokens[AgentRole.JUDGE]},
        ) as response:
            validated = json.load(response)["result"]
        self.assertEqual("PASSED", validated["validation_status"])
        self.assertEqual("PYTHON_DETERMINISTIC_GATE", validated["validated_by"])


if __name__ == "__main__":
    unittest.main()
