from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .case_store import CaseStore
from .models import JudgeRecommendation
from .policy import OutputIntegrityError, evaluate_case, validate_judge_recommendation
from .run_registry import AgentRole, RunManifestScope


CORE_GATE_A_ROLES = frozenset(
    {
        AgentRole.RIDER_ADVOCATE,
        AgentRole.DRIVER_ADVOCATE,
        AgentRole.JUDGE,
    }
)


class ProbeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AdpModelCall(ProbeArtifact):
    call_id: str = Field(min_length=1)
    role: AgentRole
    started_at: datetime
    ended_at: datetime

    @model_validator(mode="after")
    def validate_times(self) -> "AdpModelCall":
        if self.ended_at < self.started_at:
            raise ValueError("model call ended before it started")
        return self


class AdpToolCall(ProbeArtifact):
    request_id: str = Field(min_length=1)
    role: AgentRole
    operation_id: Literal[
        "get_case_snapshot",
        "get_trip_evidence",
        "get_policy_rules",
        "search_precedents",
    ]
    started_at: datetime
    ended_at: datetime
    returned_evidence_ids: tuple[str, ...] = ()
    returned_rule_ids: tuple[str, ...] = ()
    returned_precedent_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_times(self) -> "AdpToolCall":
        if self.ended_at < self.started_at:
            raise ValueError("tool call ended before it started")
        return self


class AdpTrace(ProbeArtifact):
    run_id: str
    source: Literal["ADP_EXPORTED_TRACE"]
    platform_request_id: str = Field(min_length=1)
    platform_trace_id: str = Field(min_length=1)
    workflow_started_at: datetime
    workflow_ended_at: datetime
    model_calls: tuple[AdpModelCall, ...]
    tool_calls: tuple[AdpToolCall, ...]

    @model_validator(mode="after")
    def validate_trace(self) -> "AdpTrace":
        if self.workflow_ended_at < self.workflow_started_at:
            raise ValueError("workflow ended before it started")
        model_call_ids = [item.call_id for item in self.model_calls]
        if len(model_call_ids) != len(set(model_call_ids)):
            raise ValueError("model call IDs must be unique")
        tool_request_ids = [item.request_id for item in self.tool_calls]
        if len(tool_request_ids) != len(set(tool_request_ids)):
            raise ValueError("ADP tool request IDs must be unique")
        return self


class ArtifactProvenanceReview(ProbeArtifact):
    raw_sha256: str = Field(pattern=r"^[0-9A-F]{64}$")
    platform_trace_id: str
    reviewer: str = Field(min_length=1)
    reviewed_at: datetime
    conclusion: Literal["CONFIRMED_FROM_ADP_EXPORT"]


@dataclass(frozen=True)
class AdpTraceArtifact:
    trace: AdpTrace
    raw_sha256: str
    raw_size_bytes: int
    path: Path


class AdvocateClaim(ProbeArtifact):
    statement: str
    fact_status: str
    evidence_citations: tuple[str, ...]
    policy_citations: tuple[str, ...]


class AdvocateOutput(ProbeArtifact):
    run_id: str
    stage: Literal["FINAL_ARGUMENT"]
    position: Literal["RIDER", "DRIVER"]
    claims: tuple[AdvocateClaim, ...]
    missing_evidence: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()

    @property
    def evidence_citations(self) -> set[str]:
        return {
            evidence_id
            for claim in self.claims
            for evidence_id in claim.evidence_citations
        }


class ProbeEndOutput(ProbeArtifact):
    run_id: str
    recommendation: JudgeRecommendation


@dataclass(frozen=True)
class EndOutputArtifact:
    output: ProbeEndOutput
    raw_sha256: str
    raw_size_bytes: int
    path: Path


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest().upper()


def load_adp_trace_artifact(path: Path) -> AdpTraceArtifact:
    """Load the preserved export directly. No reconstructed trace is accepted here."""
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("ADP trace artifact must be a top-level JSON object")
    return AdpTraceArtifact(
        trace=AdpTrace.model_validate(payload),
        raw_sha256=_sha256(raw),
        raw_size_bytes=len(raw),
        path=path,
    )


def load_end_output_artifact(path: Path) -> EndOutputArtifact:
    """Parse the raw End-node file and reject escaped/double-encoded JSON strings."""
    raw = path.read_bytes()
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("raw End output must be one top-level JSON object")
    return EndOutputArtifact(
        output=ProbeEndOutput.model_validate(payload),
        raw_sha256=_sha256(raw),
        raw_size_bytes=len(raw),
        path=path,
    )


def run_python_gate(
    store: CaseStore,
    scope: RunManifestScope,
    end_artifact: EndOutputArtifact,
    *,
    now: Callable[[], datetime],
) -> dict[str, Any]:
    gate_started_at = now()
    end_output = end_artifact.output
    if end_output.run_id != scope.run_id:
        raise OutputIntegrityError("End output run_id does not match the run manifest")
    snapshot = store.get_snapshot(scope.case_id, scope.case_version)
    if snapshot.policy_version != scope.policy_version:
        raise OutputIntegrityError("Run manifest policy does not match the case snapshot")
    evidence = store.get_evidence(snapshot)
    policy = store.get_policy(scope.policy_version)
    evidence_ids = set(snapshot.evidence_refs)
    policy_ids = {item["rule_id"] for item in policy.rules}
    if not set(end_output.recommendation.evidence_citations).issubset(evidence_ids):
        raise OutputIntegrityError("Judge cited evidence outside the run snapshot")
    if not set(end_output.recommendation.policy_citations).issubset(policy_ids):
        raise OutputIntegrityError("Judge cited policy outside the run policy version")
    evaluation = evaluate_case(snapshot, evidence, policy)
    validate_judge_recommendation(evaluation, end_output.recommendation)
    gate_ended_at = now()
    return {
        "run_id": scope.run_id,
        "processing_status": "RUN_COMPLETED",
        "business_status": evaluation.business_status.value,
        "matched_rule_ids": list(evaluation.matched_rule_ids),
        "allowed_action": (
            evaluation.allowed_action.model_dump(mode="json")
            if evaluation.allowed_action is not None
            else None
        ),
        "input_fingerprint": evaluation.input_fingerprint,
        "raw_end_output_sha256": end_artifact.raw_sha256,
        "gate_started_at": gate_started_at.isoformat(),
        "gate_ended_at": gate_ended_at.isoformat(),
        "validated_by": "PYTHON_DETERMINISTIC_GATE",
    }


def _successful_tool_events(
    audit_events: list[dict[str, Any]], run_id: str, role: AgentRole, endpoint: str
) -> list[dict[str, Any]]:
    return [
        item
        for item in audit_events
        if item.get("run_id") == run_id
        and item.get("actor_role") == role.value
        and item.get("endpoint") == endpoint
        and item.get("outcome") == "SUCCESS"
    ]


def _parse_timestamp(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _tool_calls_match_request_by_request(
    audit_events: list[dict[str, Any]], trace: AdpTrace
) -> tuple[bool, str]:
    operation_for_endpoint = {
        "/tools/get_case_snapshot": "get_case_snapshot",
        "/tools/get_trip_evidence": "get_trip_evidence",
        "/tools/get_policy_rules": "get_policy_rules",
        "/tools/search_precedents": "search_precedents",
    }
    adp_by_request_id = {item.request_id: item for item in trace.tool_calls}
    successful = [item for item in audit_events if item.get("outcome") == "SUCCESS"]
    mismatches: list[str] = []
    for event in successful:
        request_id = event.get("request_id")
        adp_call = adp_by_request_id.get(request_id)
        if adp_call is None:
            mismatches.append(f"{request_id}:missing_in_adp")
            continue
        expected_operation = operation_for_endpoint.get(event.get("endpoint"))
        if adp_call.operation_id != expected_operation:
            mismatches.append(f"{request_id}:operation")
        if adp_call.role.value != event.get("actor_role"):
            mismatches.append(f"{request_id}:role")
        audit_evidence = set(event.get("returned_ids", {}).get("evidence_ids", []))
        audit_rules = set(event.get("returned_ids", {}).get("rule_ids", []))
        audit_precedents = set(
            event.get("returned_ids", {}).get("precedent_ids", [])
        )
        if set(adp_call.returned_evidence_ids) != audit_evidence:
            mismatches.append(f"{request_id}:evidence_ids")
        if set(adp_call.returned_rule_ids) != audit_rules:
            mismatches.append(f"{request_id}:rule_ids")
        if set(adp_call.returned_precedent_ids) != audit_precedents:
            mismatches.append(f"{request_id}:precedent_ids")
        audit_start = _parse_timestamp(event.get("started_at"))
        audit_end = _parse_timestamp(event.get("ended_at"))
        tolerance = timedelta(seconds=5)
        if (
            audit_start is None
            or audit_end is None
            or audit_start < adp_call.started_at - tolerance
            or audit_end > adp_call.ended_at + tolerance
        ):
            mismatches.append(f"{request_id}:timestamps")
    if len(successful) != len(trace.tool_calls):
        mismatches.append(
            f"count:audit={len(successful)},adp={len(trace.tool_calls)}"
        )
    return not mismatches, ", ".join(mismatches) if mismatches else "all requests matched"


def verify_probe_artifacts(
    *,
    run_id: str,
    audit_events: list[dict[str, Any]],
    adp_artifact: AdpTraceArtifact,
    provenance_review: ArtifactProvenanceReview,
    rider_output: AdvocateOutput,
    driver_output: AdvocateOutput,
    end_artifact: EndOutputArtifact,
    python_gate_result: dict[str, Any],
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    adp_trace = adp_artifact.trace
    end_output = end_artifact.output

    def check(name: str, passed: bool, evidence: str) -> None:
        checks.append({"name": name, "passed": bool(passed), "evidence": evidence})

    check(
        "preserved_adp_export_reviewed",
        provenance_review.raw_sha256 == adp_artifact.raw_sha256
        and provenance_review.platform_trace_id == adp_trace.platform_trace_id
        and provenance_review.conclusion == "CONFIRMED_FROM_ADP_EXPORT",
        (
            "Raw artifact hash is preserved and tied to a human provenance review; "
            "this is not a Tencent cryptographic signature"
        ),
    )
    check(
        "single_run_id",
        all(
            value == run_id
            for value in (
                adp_trace.run_id,
                rider_output.run_id,
                driver_output.run_id,
                end_output.run_id,
                python_gate_result.get("run_id"),
            )
        ),
        "ADP trace, both Advocate outputs, raw End output, and Python gate share one run_id",
    )
    gate_end = _parse_timestamp(python_gate_result.get("gate_ended_at"))
    end_to_end_elapsed = (
        (gate_end - adp_trace.workflow_started_at).total_seconds()
        if gate_end is not None
        else float("inf")
    )
    check(
        "end_to_end_deadline",
        0 <= end_to_end_elapsed <= 120,
        f"ADP workflow start through Python gate end: {end_to_end_elapsed:.3f} seconds",
    )
    roles = {item.role for item in adp_trace.model_calls}
    check(
        "three_model_roles_observed",
        CORE_GATE_A_ROLES.issubset(roles),
        f"ADP exported roles: {sorted(item.value for item in roles)}",
    )
    check(
        "model_call_budget",
        3 <= len(adp_trace.model_calls) <= 7,
        f"ADP exported unique model calls: {len(adp_trace.model_calls)}",
    )

    outputs = (
        (AgentRole.RIDER_ADVOCATE, rider_output, "RIDER"),
        (AgentRole.DRIVER_ADVOCATE, driver_output, "DRIVER"),
    )
    for role, output, expected_position in outputs:
        events = _successful_tool_events(
            audit_events, run_id, role, "/tools/get_trip_evidence"
        )
        returned_evidence_ids = {
            evidence_id
            for event in events
            for evidence_id in event.get("returned_ids", {}).get("evidence_ids", [])
        }
        cited = output.evidence_citations
        prefix = role.value.lower()
        check(
            f"{prefix}_position",
            output.position == expected_position,
            f"Structured position: {output.position}",
        )
        check(
            f"{prefix}_evidence_tool_called",
            bool(events and returned_evidence_ids),
            f"Successful evidence requests: {len(events)}; returned IDs: {sorted(returned_evidence_ids)}",
        )
        check(
            f"{prefix}_citations_received_in_this_run",
            bool(cited) and cited.issubset(returned_evidence_ids),
            f"Cited IDs: {sorted(cited)}; role-specific returned IDs: {sorted(returned_evidence_ids)}",
        )

    run_audit = [item for item in audit_events if item.get("run_id") == run_id]
    requests_match, mismatch_summary = _tool_calls_match_request_by_request(
        run_audit, adp_trace
    )
    check(
        "adp_python_requests_match",
        requests_match,
        mismatch_summary,
    )
    successful_audit = [item for item in run_audit if item.get("outcome") == "SUCCESS"]
    audit_request_ids = [item.get("request_id") for item in successful_audit]
    instance_ids = {
        item.get("server_instance_id")
        for item in successful_audit
        if item.get("server_instance_id") is not None
    }
    check(
        "single_tool_server_instance",
        len(instance_ids) == 1,
        f"Observed tool server instances: {sorted(instance_ids)}",
    )
    check(
        "tool_request_ids_unique",
        bool(audit_request_ids)
        and len(audit_request_ids) == len(set(audit_request_ids))
        and None not in audit_request_ids,
        f"Successful audited tool requests: {len(audit_request_ids)}",
    )
    check(
        "raw_end_output_is_single_object",
        python_gate_result.get("raw_end_output_sha256") == end_artifact.raw_sha256,
        f"Raw End output SHA-256: {end_artifact.raw_sha256}",
    )
    check(
        "python_gate_completed",
        python_gate_result.get("processing_status") == "RUN_COMPLETED"
        and python_gate_result.get("validated_by") == "PYTHON_DETERMINISTIC_GATE",
        f"Python gate status: {python_gate_result.get('processing_status')}",
    )
    return {
        "run_id": run_id,
        "gate": "GATE_A_ADP_PROBE",
        "passed": all(item["passed"] for item in checks),
        "adp_raw_artifact_sha256": adp_artifact.raw_sha256,
        "end_raw_artifact_sha256": end_artifact.raw_sha256,
        "provenance_note": (
            "The hash preserves the reviewed artifact but does not authenticate Tencent as its signer."
        ),
        "checks": checks,
    }
