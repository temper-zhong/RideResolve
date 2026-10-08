from __future__ import annotations

import json
import io
import tempfile
import threading
import unittest
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from pydantic import ValidationError

from rideresolve.case_store import CaseStore
from rideresolve.models import BusinessStatus
from rideresolve.openapi_schema import build_openapi_schema
from rideresolve.policy import evaluate_case
from rideresolve.run_registry import AgentRole, RunRegistry, RunTokenExpiredError
from rideresolve.tool_api import create_http_server
from rideresolve.tool_audit import JsonlAuditLogger
from rideresolve.tool_service import (
    CaseSnapshotRequest,
    PolicyRulesRequest,
    ToolScope,
    ToolService,
    TripEvidenceRequest,
)


class ToolServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = CaseStore.load_default()
        cls.service = ToolService(cls.store)
        cls.scope = ToolScope(
            run_id="RUN-TEST",
            actor_role="RIDER_ADVOCATE",
            case_id="CASE-RD-TOOL-001",
            case_version=1,
            policy_version="DEMO_POLICY_V1",
        )

    def test_route_fixture_passes_deterministic_policy(self) -> None:
        snapshot = self.store.get_snapshot("CASE-RD-TOOL-001", 1)
        evidence = self.store.get_evidence(snapshot)
        policy = self.store.get_policy(snapshot.policy_version)
        result = evaluate_case(snapshot, evidence, policy)
        self.assertEqual(BusinessStatus.RESOLVED, result.business_status)
        self.assertEqual(("RD-004",), result.matched_rule_ids)
        self.assertEqual(325, result.allowed_action.amount_cents)

    def test_no_show_fixture_passes_deterministic_policy(self) -> None:
        snapshot = self.store.get_snapshot("CASE-NS-TOOL-001", 1)
        evidence = self.store.get_evidence(snapshot)
        policy = self.store.get_policy(snapshot.policy_version)
        result = evaluate_case(snapshot, evidence, policy)
        self.assertEqual(BusinessStatus.RESOLVED, result.business_status)
        self.assertEqual(("NS-002",), result.matched_rule_ids)
        self.assertEqual("NO_ACTION", result.allowed_action.type.value)

    def test_snapshot_omits_evidence_ids(self) -> None:
        response = self.service.get_case_snapshot(self.scope, CaseSnapshotRequest())
        self.assertTrue(response["synthetic"])
        self.assertNotIn("evidence_refs", response["case"])
        self.assertGreater(response["evidence_reference_count"], 0)
        self.assertIn("PLATFORM_GPS", response["available_evidence_types"])

    def test_evidence_query_is_snapshot_scoped_and_summarizes_gps(self) -> None:
        response = self.service.get_trip_evidence(
            self.scope,
            TripEvidenceRequest(evidence_types=["PLATFORM_GPS", "FARE_LEDGER"]),
        )
        self.assertEqual(2, len(response["evidence"]))
        self.assertEqual(
            {"EV-RD-GPS-FULL", "EV-RD-FARE"},
            {item["evidence_id"] for item in response["evidence"]},
        )
        self.assertAlmostEqual(100.0, response["gps_aggregate"]["coverage_percent"])
        self.assertTrue(all(item["checksum_verified"] for item in response["evidence"]))

    def test_policy_query_is_inferred_from_run_scope(self) -> None:
        response = self.service.get_policy_rules(self.scope, PolicyRulesRequest())
        ids = {rule["rule_id"] for rule in response["rules"]}
        self.assertEqual({f"RD-{index:03d}" for index in range(1, 7)}, ids)

    def test_model_cannot_add_case_scope_to_request(self) -> None:
        with self.assertRaises(ValidationError):
            CaseSnapshotRequest.model_validate(
                {"case_id": "CASE-NS-TOOL-001", "case_version": 1}
            )


class RunRegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.path = Path(self.temporary.name) / "registry.json"
        self.store = CaseStore.load_default()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_raw_tokens_are_not_persisted_and_roles_are_distinct(self) -> None:
        registry = RunRegistry(self.path, self.store)
        issued = registry.create_run("CASE-RD-TOOL-001", 1)
        persisted = self.path.read_text(encoding="utf-8")
        for token in issued.tokens.values():
            self.assertNotIn(token, persisted)
        rider = registry.authorize_and_consume(issued.tokens[AgentRole.RIDER_ADVOCATE])
        driver = registry.authorize_and_consume(issued.tokens[AgentRole.DRIVER_ADVOCATE])
        self.assertEqual(issued.run_id, rider.run_id)
        self.assertEqual(AgentRole.RIDER_ADVOCATE, rider.role)
        self.assertEqual(AgentRole.DRIVER_ADVOCATE, driver.role)

    def test_expired_token_is_rejected(self) -> None:
        current = datetime(2026, 10, 7, tzinfo=UTC)
        registry = RunRegistry(self.path, self.store, now=lambda: current)
        issued = registry.create_run("CASE-RD-TOOL-001", 1, ttl_seconds=60)
        expired_registry = RunRegistry(
            self.path,
            self.store,
            now=lambda: current + timedelta(seconds=61),
        )
        with self.assertRaises(RunTokenExpiredError):
            expired_registry.authorize_and_consume(
                issued.tokens[AgentRole.RIDER_ADVOCATE]
            )


class ToolHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.root = Path(cls.temporary.name)
        cls.service = ToolService.load_default()
        cls.registry = RunRegistry(cls.root / "registry.json", cls.service.store)
        cls.audit = JsonlAuditLogger(cls.root / "audit.jsonl")
        cls.issued = cls.registry.create_run("CASE-RD-TOOL-001", 1)
        cls.server = create_http_server(
            "127.0.0.1",
            0,
            registry=cls.registry,
            audit_logger=cls.audit,
            service=cls.service,
            openapi_server_url="https://probe.example.invalid",
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

    def post(
        self,
        path: str,
        payload: dict,
        *,
        token: str | None = None,
        supplied_request_id: str | None = None,
    ):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["X-RideResolve-Run-Token"] = token
        if supplied_request_id is not None:
            headers["X-Request-Id"] = supplied_request_id
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        return urlopen(request, timeout=5)

    def test_health_and_fixed_openapi_are_available(self) -> None:
        with urlopen(self.base_url + "/health", timeout=5) as response:
            body = json.load(response)
        self.assertEqual("ok", body["status"])
        with urlopen(self.base_url + "/openapi.json", timeout=5) as response:
            schema = json.load(response)
        self.assertEqual("https://probe.example.invalid", schema["servers"][0]["url"])
        self.assertEqual(
            "X-RideResolve-Run-Token",
            schema["components"]["securitySchemes"]["RunToken"]["name"],
        )

    def test_tool_requires_run_token(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            self.post("/tools/get_case_snapshot", {})
        self.assertEqual(401, caught.exception.code)

    def test_authorized_snapshot_hides_evidence_ids(self) -> None:
        with self.post(
            "/tools/get_case_snapshot",
            {},
            token=self.issued.tokens[AgentRole.RIDER_ADVOCATE],
        ) as response:
            body = json.load(response)
        self.assertEqual(self.issued.run_id, body["result"]["run_id"])
        self.assertEqual("RIDER_ADVOCATE", body["result"]["tool_actor_role"])
        self.assertNotIn("evidence_refs", body["result"]["case"])

    def test_model_cannot_switch_case(self) -> None:
        with self.assertRaises(HTTPError) as caught:
            self.post(
                "/tools/get_case_snapshot",
                {"case_id": "CASE-NS-TOOL-001", "case_version": 1},
                token=self.issued.tokens[AgentRole.RIDER_ADVOCATE],
            )
        self.assertEqual(422, caught.exception.code)

    def test_secret_like_invalid_values_never_reach_response_jsonl_or_stdout(self) -> None:
        fake_secret = "FAKE_SECRET_DO_NOT_LOG_7ef49c"
        before = len(self.audit.read_all())
        output = io.StringIO()
        self.audit.emit_stdout = True
        try:
            with redirect_stdout(output):
                with self.assertRaises(HTTPError) as caught:
                    self.post(
                        "/tools/get_case_snapshot",
                        {fake_secret: fake_secret, "case_id": fake_secret},
                        token=self.issued.tokens[AgentRole.DRIVER_ADVOCATE],
                    )
                response_body = caught.exception.read().decode("utf-8")
        finally:
            self.audit.emit_stdout = False
        new_events = self.audit.read_all()[before:]
        self.assertEqual(1, len(new_events))
        serialized_event = json.dumps(new_events[0], ensure_ascii=False)
        self.assertNotIn(fake_secret, response_body)
        self.assertNotIn(fake_secret, serialized_event)
        self.assertNotIn(fake_secret, output.getvalue())
        self.assertEqual("VALIDATION_ERROR", new_events[0]["error_code"])

    def test_secret_like_request_id_header_is_ignored_and_never_logged(self) -> None:
        fake_secret = "FAKE_HEADER_SECRET_DO_NOT_LOG_9f6e2d7a"
        before = len(self.audit.read_all())
        output = io.StringIO()
        self.audit.emit_stdout = True
        try:
            with redirect_stdout(output):
                with self.post(
                    "/tools/get_case_snapshot",
                    {},
                    token=self.issued.tokens[AgentRole.JUDGE],
                    supplied_request_id=fake_secret,
                ) as response:
                    response_body = response.read().decode("utf-8")
        finally:
            self.audit.emit_stdout = False
        new_events = self.audit.read_all()[before:]
        self.assertEqual(1, len(new_events))
        serialized_event = json.dumps(new_events[0], ensure_ascii=False)
        self.assertNotIn(fake_secret, response_body)
        self.assertNotIn(fake_secret, serialized_event)
        self.assertNotIn(fake_secret, output.getvalue())
        returned_request_id = json.loads(response_body)["request_id"]
        self.assertRegex(returned_request_id, r"^rr-[0-9a-f]{32}$")
        self.assertEqual(returned_request_id, new_events[0]["request_id"])

    def test_rider_and_driver_evidence_calls_are_independently_audited(self) -> None:
        for role in (AgentRole.RIDER_ADVOCATE, AgentRole.DRIVER_ADVOCATE):
            with self.post(
                "/tools/get_trip_evidence",
                {"evidence_types": ["FARE_LEDGER"]},
                token=self.issued.tokens[role],
            ) as response:
                body = json.load(response)
            self.assertEqual(role.value, body["result"]["tool_actor_role"])
        events = [
            item
            for item in self.audit.read_all()
            if item["run_id"] == self.issued.run_id
            and item["endpoint"] == "/tools/get_trip_evidence"
            and item["outcome"] == "SUCCESS"
        ]
        self.assertEqual(
            {"RIDER_ADVOCATE", "DRIVER_ADVOCATE"},
            {item["actor_role"] for item in events},
        )
        self.assertTrue(all(item["returned_ids"]["evidence_ids"] == ["EV-RD-FARE"] for item in events))
        audit_text = (self.root / "audit.jsonl").read_text(encoding="utf-8")
        for token in self.issued.tokens.values():
            self.assertNotIn(token, audit_text)

    def test_request_limit_returns_429(self) -> None:
        limited = self.registry.create_run(
            "CASE-RD-TOOL-001", 1, max_requests_per_role=1
        )
        token = limited.tokens[AgentRole.JUDGE]
        with self.post("/tools/get_policy_rules", {}, token=token):
            pass
        with self.assertRaises(HTTPError) as caught:
            self.post("/tools/get_policy_rules", {}, token=token)
        self.assertEqual(429, caught.exception.code)

    def test_http_openapi_url_is_rejected_by_builder(self) -> None:
        with self.assertRaises(ValueError):
            build_openapi_schema("http://example.com")


if __name__ == "__main__":
    unittest.main()
