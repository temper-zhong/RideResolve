from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from .case_store import CaseStore
from .models import BusinessStatus, DisputeType, SourceType
from .tool_service import (
    CaseSnapshotRequest,
    PolicyRulesRequest,
    ToolScope,
    ToolService,
    TripEvidenceRequest,
)

if TYPE_CHECKING:
    from .demo_service import EvaluatedDemoCase


@dataclass(frozen=True)
class EvidenceCollectionStep:
    operation: str
    purpose: str
    requested_source_types: tuple[str, ...]
    returned_evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvidenceCollectionReport:
    agent_name: Literal["Evidence Collection Agent"]
    execution_mode: Literal["SYNTHETIC_OFFLINE"]
    case_id: str
    case_version: int
    dispute_type: DisputeType
    required_source_types: tuple[str, ...]
    collected_source_types: tuple[str, ...]
    collected_evidence_ids: tuple[str, ...]
    policy_rule_ids: tuple[str, ...]
    steps: tuple[EvidenceCollectionStep, ...]
    gaps: tuple[str, ...]
    ready_for_advocates: bool
    summary: str


@dataclass(frozen=True)
class EscalationPacket:
    capability_name: Literal["Escalation Protocol"]
    triggered: bool
    effective_status: BusinessStatus
    queue: str | None
    priority: Literal["STANDARD", "NONE"]
    threshold: int
    judge_confidence: int
    trigger_reasons: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    matched_rule_ids: tuple[str, ...]
    recommended_next_step: str
    case_summary: str


_COLLECTION_PLAN: dict[DisputeType, tuple[tuple[SourceType, ...], tuple[SourceType, ...]]] = {
    DisputeType.ROUTE_DEVIATION: (
        (
            SourceType.PLATFORM_GPS,
            SourceType.ROUTE_BASELINE,
            SourceType.FARE_LEDGER,
        ),
        (
            SourceType.AUTHENTICATED_CHAT,
            SourceType.DEMO_TRAFFIC_FEED,
            SourceType.HISTORICAL_BEHAVIOR_PROFILE,
        ),
    ),
    DisputeType.NO_SHOW: (
        (
            SourceType.PLATFORM_GPS,
            SourceType.TRIP_EVENT_LOG,
            SourceType.CONTACT_LOG,
            SourceType.FARE_LEDGER,
        ),
        (SourceType.HISTORICAL_BEHAVIOR_PROFILE,),
    ),
    DisputeType.FARE_DISPUTE: (
        (
            SourceType.FARE_LEDGER,
            SourceType.SURGE_PRICING_LOG,
            SourceType.NOTIFICATION_LOG,
        ),
        (
            SourceType.AUTHENTICATED_CHAT,
            SourceType.HISTORICAL_BEHAVIOR_PROFILE,
        ),
    ),
}


def run_evidence_collection_agent(
    store: CaseStore,
    case_id: str,
    case_version: int,
) -> EvidenceCollectionReport:
    """Run the bounded offline collector against the same tools exposed to ADP.

    The collector chooses its query plan from the dispute type, verifies that the
    returned records belong to the requested snapshot, and reports gaps. It never
    evaluates liability, selects an outcome, or calculates money.
    """
    snapshot = store.get_snapshot(case_id, case_version)
    required_types, contextual_types = _COLLECTION_PLAN[snapshot.dispute_type]
    scope = ToolScope(
        run_id=f"SYNTHETIC-COLLECTOR-{case_id}-V{case_version}",
        actor_role="EVIDENCE_COLLECTION_AGENT",
        case_id=case_id,
        case_version=case_version,
        policy_version=snapshot.policy_version,
    )
    service = ToolService(store)

    case_response = service.get_case_snapshot(scope, CaseSnapshotRequest())
    core_response = service.get_trip_evidence(
        scope,
        TripEvidenceRequest(evidence_types=list(required_types), detail="SUMMARY"),
    )
    context_response = service.get_trip_evidence(
        scope,
        TripEvidenceRequest(evidence_types=list(contextual_types), detail="SUMMARY"),
    )
    policy_response = service.get_policy_rules(scope, PolicyRulesRequest())

    core_records = core_response["evidence"]
    context_records = context_response["evidence"]
    all_records = [*core_records, *context_records]
    collected_ids = tuple(str(item["evidence_id"]) for item in all_records)
    collected_types = tuple(sorted({str(item["source_type"]) for item in all_records}))
    policy_rule_ids = tuple(str(rule["rule_id"]) for rule in policy_response["rules"])

    present_types = set(collected_types)
    gaps = [
        f"Missing required source: {source_type.value}"
        for source_type in required_types
        if source_type.value not in present_types
    ]
    invalid_checksums = [
        str(item["evidence_id"])
        for item in all_records
        if not item.get("checksum_verified", False)
    ]
    if invalid_checksums:
        gaps.append("Checksum verification failed: " + ", ".join(invalid_checksums))

    if (
        snapshot.dispute_type == DisputeType.ROUTE_DEVIATION
        and snapshot.policy_version == "DEMO_POLICY_V1"
    ):
        gps = core_response.get("gps_aggregate", {})
        coverage = float(gps.get("coverage_percent", 0.0))
        if gps.get("conflict", False):
            gaps.append("Authoritative GPS segments conflict and require review")
        if coverage < 90.0:
            gaps.append(f"GPS coverage is {coverage:.1f}%; at least 90.0% is required")

    steps = (
        EvidenceCollectionStep(
            operation="get_case_snapshot",
            purpose="Discover the dispute type and available evidence sources.",
            requested_source_types=(),
            returned_evidence_ids=(),
        ),
        EvidenceCollectionStep(
            operation="get_trip_evidence",
            purpose="Retrieve the policy-required evidence package.",
            requested_source_types=tuple(item.value for item in required_types),
            returned_evidence_ids=tuple(str(item["evidence_id"]) for item in core_records),
        ),
        EvidenceCollectionStep(
            operation="get_trip_evidence",
            purpose="Retrieve non-decisional context for the Advocate agents.",
            requested_source_types=tuple(item.value for item in contextual_types),
            returned_evidence_ids=tuple(str(item["evidence_id"]) for item in context_records),
        ),
        EvidenceCollectionStep(
            operation="get_policy_rules",
            purpose="Attach the version-pinned policy rules without evaluating an outcome.",
            requested_source_types=(),
            returned_evidence_ids=(),
        ),
    )
    ready = not gaps
    summary = (
        f"Collected {len(collected_ids)} records across {len(collected_types)} source types; "
        + ("the evidence package is ready for both Advocates." if ready else "the package is held for supplementation.")
    )
    if case_response["evidence_reference_count"] < len(collected_ids):
        raise ValueError("collector returned more evidence records than the snapshot references")

    return EvidenceCollectionReport(
        agent_name="Evidence Collection Agent",
        execution_mode="SYNTHETIC_OFFLINE",
        case_id=case_id,
        case_version=case_version,
        dispute_type=snapshot.dispute_type,
        required_source_types=tuple(item.value for item in required_types),
        collected_source_types=collected_types,
        collected_evidence_ids=collected_ids,
        policy_rule_ids=policy_rule_ids,
        steps=steps,
        gaps=tuple(gaps),
        ready_for_advocates=ready,
        summary=summary,
    )


def build_escalation_packet(
    case: EvaluatedDemoCase,
    confidence_threshold: int = 70,
) -> EscalationPacket:
    """Create a human-review packet from policy and Judge uncertainty signals.

    Judge confidence is allowed to trigger a safe escalation but can never release
    a case. Deterministic review requirements always take precedence.
    """
    if not 0 <= confidence_threshold <= 100:
        raise ValueError("confidence_threshold must be between 0 and 100")

    reasons: list[str] = []
    if case.evaluation.business_status == BusinessStatus.PENDING_HUMAN_REVIEW:
        if case.evaluation.review_reasons:
            reasons.extend(
                f"Deterministic gate: {reason}" for reason in case.evaluation.review_reasons
            )
        else:
            reasons.append("Deterministic policy requires human review")

    confidence = case.judge.judge_confidence.score
    if confidence < confidence_threshold:
        reasons.append(
            f"Judge self-confidence {confidence}/100 is below the escalation threshold "
            f"of {confidence_threshold}/100"
        )

    triggered = bool(reasons)
    if triggered and case.snapshot.dispute_type == DisputeType.ROUTE_DEVIATION:
        next_step = "Review GPS completeness or conflicts, then rerun the same policy version."
    elif triggered:
        next_step = "Review arrival, waiting, and contact records, then rerun the same policy version."
    else:
        next_step = "No human handoff is required; deterministic release gates remain authoritative."

    evidence_ids = tuple(item.evidence_id for item in case.evidence)
    rules = tuple(case.evaluation.matched_rule_ids)
    summary = (
        f"{case.snapshot.case_id} v{case.snapshot.case_version} | "
        f"{case.snapshot.dispute_type.value} | policy {case.snapshot.policy_version} | "
        f"rules {', '.join(rules) or 'none'} | {len(evidence_ids)} cited evidence records."
    )

    return EscalationPacket(
        capability_name="Escalation Protocol",
        triggered=triggered,
        effective_status=(
            BusinessStatus.PENDING_HUMAN_REVIEW
            if triggered
            else case.evaluation.business_status
        ),
        queue="HUMAN_DISPUTE_REVIEW" if triggered else None,
        priority="STANDARD" if triggered else "NONE",
        threshold=confidence_threshold,
        judge_confidence=confidence,
        trigger_reasons=tuple(reasons),
        evidence_ids=evidence_ids,
        matched_rule_ids=rules,
        recommended_next_step=next_step,
        case_summary=summary,
    )
