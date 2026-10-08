from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rideresolve.case_store import CaseStore
from rideresolve.probe_validation import (
    AdpModelCall,
    AdpToolCall,
    AdpTrace,
    AdvocateOutput,
    ArtifactProvenanceReview,
    load_adp_trace_artifact,
    load_end_output_artifact,
    run_python_gate,
    verify_probe_artifacts,
)
from rideresolve.run_registry import AgentRole, RunManifestScope


RUN_ID = "RUN-PROBE-TEST"
START = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)


def advocate(position: str, evidence_id: str) -> AdvocateOutput:
    return AdvocateOutput.model_validate(
        {
            "run_id": RUN_ID,
            "stage": "FINAL_ARGUMENT",
            "position": position,
            "claims": [
                {
                    "statement": "Verified claim",
                    "fact_status": "PROVEN",
                    "evidence_citations": [evidence_id],
                    "policy_citations": ["RD-004"],
                }
            ],
        }
    )


def end_payload() -> dict:
    return {
        "run_id": RUN_ID,
        "recommendation": {
            "recommended_case_status": "RESOLVED",
            "recommended_action": {
                "type": "REFUND_DISPUTED_FEE_FULL",
                "fee_item": "distance_surcharge",
                "amount_cents": 325,
                "currency": "SGD",
            },
            "evidence_citations": ["EV-RD-GPS-FULL", "EV-RD-BASELINE", "EV-RD-FARE"],
            "policy_citations": ["RD-004"],
            "judge_confidence": {
                "score": 90,
                "label": "UNCALIBRATED_MODEL_SELF_ASSESSMENT",
                "rationale": "Synthetic probe rationale",
            },
            "reasoning_summary": "The deterministic RD-004 conditions are satisfied.",
            "uncertainties": [],
            "rider_explanation": "Synthetic explanation for the rider.",
            "driver_explanation": "Synthetic explanation for the driver.",
        },
    }


def audit(role: AgentRole, evidence_id: str, request_id: str, offset: int) -> dict:
    return {
        "run_id": RUN_ID,
        "actor_role": role.value,
        "endpoint": "/tools/get_trip_evidence",
        "outcome": "SUCCESS",
        "request_id": request_id,
        "server_instance_id": "INSTANCE-PROBE-TEST",
        "started_at": (START + timedelta(seconds=offset)).isoformat(),
        "ended_at": (START + timedelta(seconds=offset + 1)).isoformat(),
        "returned_ids": {"evidence_ids": [evidence_id], "rule_ids": []},
    }


class ProbeValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.store = CaseStore.load_default()
        self.scope = RunManifestScope(
            run_id=RUN_ID,
            case_id="CASE-RD-TOOL-001",
            case_version=1,
            policy_version="DEMO_POLICY_V1",
            created_at=START,
            expires_at=START + timedelta(hours=1),
            status="ACTIVE",
        )
        end_path = self.root / "raw_end.json"
        end_path.write_text(json.dumps(end_payload()), encoding="utf-8")
        self.end_artifact = load_end_output_artifact(end_path)
        moments = iter([START + timedelta(seconds=31), START + timedelta(seconds=32)])
        self.gate = run_python_gate(
            self.store, self.scope, self.end_artifact, now=lambda: next(moments)
        )
        self.events = [
            audit(AgentRole.RIDER_ADVOCATE, "EV-RD-GPS-FULL", "REQ-RIDER", 10),
            audit(AgentRole.DRIVER_ADVOCATE, "EV-RD-FARE", "REQ-DRIVER", 20),
        ]

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def make_trace_artifact(self, call_count: int = 3, *, driver_request_id: str = "REQ-DRIVER"):
        roles = [AgentRole.RIDER_ADVOCATE, AgentRole.DRIVER_ADVOCATE, AgentRole.JUDGE]
        model_calls = [
            AdpModelCall(
                call_id=f"CALL-{index}",
                role=roles[index % len(roles)],
                started_at=START + timedelta(seconds=index),
                ended_at=START + timedelta(seconds=index + 1),
            )
            for index in range(call_count)
        ]
        tool_calls = [
            AdpToolCall(
                request_id="REQ-RIDER",
                role=AgentRole.RIDER_ADVOCATE,
                operation_id="get_trip_evidence",
                started_at=START + timedelta(seconds=9),
                ended_at=START + timedelta(seconds=12),
                returned_evidence_ids=("EV-RD-GPS-FULL",),
            ),
            AdpToolCall(
                request_id=driver_request_id,
                role=AgentRole.DRIVER_ADVOCATE,
                operation_id="get_trip_evidence",
                started_at=START + timedelta(seconds=19),
                ended_at=START + timedelta(seconds=22),
                returned_evidence_ids=("EV-RD-FARE",),
            ),
        ]
        trace = AdpTrace(
            run_id=RUN_ID,
            source="ADP_EXPORTED_TRACE",
            platform_request_id="ADP-REQUEST-001",
            platform_trace_id="ADP-TRACE-001",
            workflow_started_at=START,
            workflow_ended_at=START + timedelta(seconds=30),
            model_calls=tuple(model_calls),
            tool_calls=tuple(tool_calls),
        )
        path = self.root / f"adp_trace_{call_count}_{driver_request_id}.json"
        path.write_text(trace.model_dump_json(), encoding="utf-8")
        return load_adp_trace_artifact(path)

    def verify(
        self,
        *,
        rider_id: str = "EV-RD-GPS-FULL",
        model_calls: int = 3,
        driver_request_id: str = "REQ-DRIVER",
        gate_result: dict | None = None,
    ):
        artifact = self.make_trace_artifact(model_calls, driver_request_id=driver_request_id)
        review = ArtifactProvenanceReview(
            raw_sha256=artifact.raw_sha256,
            platform_trace_id=artifact.trace.platform_trace_id,
            reviewer="TEST_REVIEWER",
            reviewed_at=START + timedelta(seconds=33),
            conclusion="CONFIRMED_FROM_ADP_EXPORT",
        )
        return verify_probe_artifacts(
            run_id=RUN_ID,
            audit_events=self.events,
            adp_artifact=artifact,
            provenance_review=review,
            rider_output=advocate("RIDER", rider_id),
            driver_output=advocate("DRIVER", "EV-RD-FARE"),
            end_artifact=self.end_artifact,
            python_gate_result=gate_result or self.gate,
        )

    def test_complete_probe_evidence_passes(self) -> None:
        self.assertTrue(self.verify()["passed"])

    def test_true_but_unreturned_evidence_id_fails_role_check(self) -> None:
        report = self.verify(rider_id="EV-RD-BASELINE")
        self.assertFalse(report["passed"])
        failed = {item["name"] for item in report["checks"] if not item["passed"]}
        self.assertIn("rider_advocate_citations_received_in_this_run", failed)

    def test_more_than_seven_model_calls_fails(self) -> None:
        report = self.verify(model_calls=8)
        self.assertFalse(report["passed"])
        failed = {item["name"] for item in report["checks"] if not item["passed"]}
        self.assertIn("model_call_budget", failed)

    def test_request_id_mismatch_fails_cross_system_check(self) -> None:
        report = self.verify(driver_request_id="WRONG-REQUEST")
        self.assertFalse(report["passed"])
        failed = {item["name"] for item in report["checks"] if not item["passed"]}
        self.assertIn("adp_python_requests_match", failed)

    def test_double_encoded_raw_end_output_is_rejected(self) -> None:
        path = self.root / "escaped_end.json"
        path.write_text(json.dumps(json.dumps(end_payload())), encoding="utf-8")
        with self.assertRaises(ValueError):
            load_end_output_artifact(path)

    def test_deadline_includes_python_gate_completion(self) -> None:
        late_gate = dict(self.gate)
        late_gate["gate_ended_at"] = (START + timedelta(seconds=121)).isoformat()
        report = self.verify(gate_result=late_gate)
        self.assertFalse(report["passed"])
        failed = {item["name"] for item in report["checks"] if not item["passed"]}
        self.assertIn("end_to_end_deadline", failed)


if __name__ == "__main__":
    unittest.main()
