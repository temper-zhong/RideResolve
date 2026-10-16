from __future__ import annotations

from dataclasses import dataclass

from .case_store import CaseStore
from .delta import build_decision_delta
from .models import (
    ActionType,
    BusinessStatus,
    CaseSnapshot,
    DecisionDelta,
    DisputeType,
    Evidence,
    JudgeConfidence,
    JudgeRecommendation,
    PolicyEvaluation,
    SourceType,
)
from .policy import PolicyFile, evaluate_case, validate_judge_recommendation


@dataclass(frozen=True)
class EvaluatedDemoCase:
    snapshot: CaseSnapshot
    evidence: tuple[Evidence, ...]
    policy: PolicyFile
    evaluation: PolicyEvaluation
    judge: JudgeRecommendation


@dataclass(frozen=True)
class DeltaDemo:
    before: EvaluatedDemoCase
    after: EvaluatedDemoCase
    delta: DecisionDelta


def synthetic_judge(
    evaluation: PolicyEvaluation,
    evidence_ids: tuple[str, ...],
) -> JudgeRecommendation:
    """Build an explicitly synthetic Judge record for the offline UI only."""
    if evaluation.business_status == BusinessStatus.PENDING_HUMAN_REVIEW:
        reason = evaluation.review_reasons[0] if evaluation.review_reasons else "Evidence is insufficient."
        summary = f"Recommend human review. {reason}"
        rider_explanation = "We cannot issue an automated ruling because the required evidence is incomplete."
        driver_explanation = "No automated action is taken while the required evidence remains incomplete."
        confidence = 58
    elif evaluation.allowed_action and evaluation.allowed_action.type == ActionType.NO_ACTION:
        summary = "Recommend no action because the deterministic policy conditions for the charge are satisfied."
        rider_explanation = "The reviewed platform records support the charge under the fixed demo policy."
        driver_explanation = "The reviewed platform records support no corrective action under the fixed demo policy."
        confidence = 76
    else:
        summary = "Recommend the program-allowed simulated refund shown below."
        rider_explanation = "The fixed demo policy permits a simulated refund of the disputed fee item."
        driver_explanation = "The fixed demo policy permits a simulated refund; no real payment was executed."
        confidence = 74

    return JudgeRecommendation(
        recommended_case_status=evaluation.business_status,
        recommended_action=evaluation.allowed_action,
        evidence_citations=evidence_ids,
        policy_citations=evaluation.matched_rule_ids,
        judge_confidence=JudgeConfidence(
            score=confidence,
            label="UNCALIBRATED_MODEL_SELF_ASSESSMENT",
            rationale="Synthetic offline UI fixture; this value never controls release.",
        ),
        reasoning_summary=summary,
        uncertainties=evaluation.review_reasons,
        rider_explanation=rider_explanation,
        driver_explanation=driver_explanation,
    )


def evaluate_demo_case(
    store: CaseStore,
    case_id: str,
    case_version: int,
) -> EvaluatedDemoCase:
    snapshot = store.get_snapshot(case_id, case_version)
    evidence = tuple(store.get_evidence(snapshot))
    policy = store.get_policy(snapshot.policy_version)
    evaluation = evaluate_case(snapshot, list(evidence), policy)
    judge = synthetic_judge(evaluation, tuple(item.evidence_id for item in evidence))
    validate_judge_recommendation(evaluation, judge)
    return EvaluatedDemoCase(snapshot, evidence, policy, evaluation, judge)


def load_delta_demo(store: CaseStore | None = None) -> DeltaDemo:
    store = store or CaseStore.load_default()
    before = evaluate_demo_case(store, "CASE-RD-001", 1)
    after = evaluate_demo_case(store, "CASE-RD-001", 2)
    delta = build_decision_delta(
        before.snapshot,
        after.snapshot,
        before.evaluation,
        after.evaluation,
        before.judge,
        after.judge,
        evidence=list(after.evidence),
        policy=after.policy,
    )
    return DeltaDemo(before, after, delta)


def program_evidence_sufficiency(case: EvaluatedDemoCase) -> int:
    """Uncalibrated display-only completeness score; never an auto-release gate."""
    if case.snapshot.dispute_type == DisputeType.ROUTE_DEVIATION:
        return max(0, min(100, round(case.evaluation.metrics.get("gps_coverage_percent", 0))))
    required = {
        SourceType.PLATFORM_GPS,
        SourceType.TRIP_EVENT_LOG,
        SourceType.CONTACT_LOG,
        SourceType.FARE_LEDGER,
    }
    present = {item.source_type for item in case.evidence}
    return round(100 * len(required & present) / len(required))


def chat_semantic_signals(case: EvaluatedDemoCase) -> list[dict[str, object]]:
    """Return transparent synthetic annotations without treating them as facts."""
    rows: list[dict[str, object]] = []
    for item in case.evidence:
        if item.source_type != SourceType.AUTHENTICATED_CHAT:
            continue
        messages = item.payload.get("messages", [])
        if not isinstance(messages, list):
            continue
        for message in messages:
            if not isinstance(message, dict):
                continue
            labels = message.get("synthetic_semantic_labels", {})
            if not isinstance(labels, dict):
                labels = {}
            rows.append(
                {
                    "Message": str(message.get("message_id", "unknown")),
                    "Speaker": str(message.get("sender", "unknown")),
                    "Sentiment": str(labels.get("sentiment", "UNKNOWN")),
                    "Consent": str(labels.get("consent", "UNKNOWN")),
                    "Disagreement": bool(labels.get("disagreement", False)),
                    "Threat": bool(labels.get("threat", False)),
                    "Evidence": item.evidence_id,
                }
            )
    return rows


def historical_context_rows(case: EvaluatedDemoCase) -> list[dict[str, object]]:
    """Return supporting history fields that are explicitly excluded from decisions."""
    rows: list[dict[str, object]] = []
    for item in case.evidence:
        if item.source_type != SourceType.HISTORICAL_BEHAVIOR_PROFILE:
            continue
        profiles = item.payload.get("profiles", [])
        if not isinstance(profiles, list):
            continue
        for profile in profiles:
            if not isinstance(profile, dict):
                continue
            rows.append(
                {
                    "Party": str(profile.get("party", "UNKNOWN")),
                    "Account age": f"{int(profile.get('account_age_days', 0))} days",
                    "Completed trips": int(profile.get("completed_trips", 0)),
                    "Prior disputes (180d)": int(profile.get("prior_disputes_180d", 0)),
                    "Rating pattern": str(profile.get("rating_pattern", "UNKNOWN")),
                    "Decision use": "CONTEXT ONLY",
                }
            )
    return rows


def gate_rows(case: EvaluatedDemoCase) -> list[dict[str, str]]:
    evaluation = case.evaluation
    gps_coverage = evaluation.metrics.get("gps_coverage_percent")
    required_evidence_passed = not (
        case.snapshot.dispute_type == DisputeType.ROUTE_DEVIATION
        and gps_coverage is not None
        and gps_coverage < 90
    )
    amount = evaluation.allowed_action.amount_cents if evaluation.allowed_action else 0
    amount_passed = amount <= case.snapshot.disputed_amount_cents
    rows = [
        {
            "Gate": "Evidence integrity + input fingerprint",
            "Result": "PASS" if evaluation.input_fingerprint.startswith("sha256:") else "FAIL",
            "Evidence": evaluation.input_fingerprint[:22] + "...",
        },
        {
            "Gate": "Policy version and effective period",
            "Result": "PASS",
            "Evidence": case.snapshot.policy_version,
        },
        {
            "Gate": "Required evidence completeness",
            "Result": "PASS" if required_evidence_passed else "BLOCKED AS DESIGNED",
            "Evidence": (
                f"GPS coverage {gps_coverage:.1f}% / 90.0% required"
                if gps_coverage is not None
                else "Required source set checked"
            ),
        },
        {
            "Gate": "Judge recommendation vs program action",
            "Result": "PASS",
            "Evidence": "Exact status and action match",
        },
        {
            "Gate": "Refund item and amount bound",
            "Result": "PASS" if amount_passed else "FAIL",
            "Evidence": f"SGD {amount / 100:.2f} / disputed SGD {case.snapshot.disputed_amount_cents / 100:.2f}",
        },
    ]
    return rows


def advocate_panels(
    case: EvaluatedDemoCase,
    collected_evidence_ids: tuple[str, ...] | None = None,
) -> tuple[dict, dict]:
    package_ids = (
        set(collected_evidence_ids)
        if collected_evidence_ids is not None
        else {item.evidence_id for item in case.evidence}
    )
    case_ids = {item.evidence_id for item in case.evidence}
    if not package_ids <= case_ids:
        raise ValueError("Advocate evidence package contains IDs outside the case snapshot")

    if case.snapshot.dispute_type == DisputeType.ROUTE_DEVIATION:
        rider_sources = {SourceType.PLATFORM_GPS, SourceType.FARE_LEDGER, SourceType.ROUTE_BASELINE}
        driver_sources = {SourceType.PLATFORM_GPS, SourceType.AUTHENTICATED_CHAT, SourceType.DEMO_TRAFFIC_FEED}
        coverage = case.evaluation.metrics.get("gps_coverage_percent", 0)
        rider_argument = (
            f"GPS coverage is {coverage:.1f}%. The deterministic policy currently permits "
            + ("a simulated distance-surcharge refund." if case.evaluation.allowed_action else "human review only.")
        )
        driver_argument = (
            "I checked the platform GPS and the two verifiable exception channels. "
            "No exception is asserted beyond what those records can prove."
        )
    else:
        rider_sources = {SourceType.PLATFORM_GPS, SourceType.TRIP_EVENT_LOG, SourceType.FARE_LEDGER}
        driver_sources = {SourceType.PLATFORM_GPS, SourceType.TRIP_EVENT_LOG, SourceType.CONTACT_LOG}
        rider_argument = "I checked pickup distance, event timestamps, and the charged fee item."
        driver_argument = "I checked arrival, waiting duration, and the in-app contact attempt."

    def panel(role: str, sources: set[SourceType], argument: str) -> dict:
        citations = [
            item.evidence_id
            for item in case.evidence
            if item.evidence_id in package_ids and item.source_type in sources
        ]
        return {
            "role": role,
            "queries": [
                "get_case_snapshot()",
                "get_trip_evidence(source_types=...)",
                f"policy={case.snapshot.policy_version} (Python-pinned)",
            ],
            "citations": citations,
            "argument": argument,
        }

    return (
        panel("Rider Advocate", rider_sources, rider_argument),
        panel("Driver Advocate", driver_sources, driver_argument),
    )
