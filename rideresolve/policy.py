from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from .gps import aggregate_gps
from .integrity import compute_input_fingerprint, index_evidence
from .models import (
    Action,
    ActionType,
    BusinessStatus,
    CaseSnapshot,
    DisputeType,
    Evidence,
    FactStatus,
    JudgeRecommendation,
    PolicyEvaluation,
    SourceType,
    TrustTier,
)


class PolicyFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: str
    policy_version: str
    effective_from: str
    effective_to: str | None
    timezone: str
    rules: tuple[dict[str, Any], ...]


class OutputIntegrityError(ValueError):
    """The model output conflicts with deterministic policy evaluation."""


EXPECTED_RULE_CONTRACTS: dict[str, dict[str, Any]] = {
    "RD-001": {
        "evaluator": "route_deviation_required_evidence",
        "parameters": {
            "minimum_gps_coverage_percent": 90,
            "required_source_types": ["PLATFORM_GPS", "ROUTE_BASELINE", "FARE_LEDGER"],
        },
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
    "RD-002": {
        "evaluator": "route_deviation_within_tolerance",
        "parameters": {"maximum_allowed_ratio": 1.2},
        "allowed_outcome": {"action": "NO_ACTION"},
    },
    "RD-003": {
        "evaluator": "route_deviation_verified_exception",
        "parameters": {"verifiable_exception_sources": ["AUTHENTICATED_CHAT", "DEMO_TRAFFIC_FEED"]},
        "allowed_outcome": {"action": "NO_ACTION"},
    },
    "RD-004": {
        "evaluator": "route_deviation_unjustified_surcharge",
        "parameters": {"fee_item": "distance_surcharge"},
        "allowed_outcome": {"action": "REFUND_DISPUTED_FEE_FULL"},
    },
    "RD-005": {
        "evaluator": "route_deviation_uncertain_exception",
        "parameters": {},
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
    "RD-006": {
        "evaluator": "route_deviation_unverifiable_oral_claim",
        "parameters": {},
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
    "NS-001": {
        "evaluator": "no_show_required_evidence",
        "parameters": {"required_source_types": ["PLATFORM_GPS", "TRIP_EVENT_LOG", "CONTACT_LOG", "FARE_LEDGER"]},
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
    "NS-002": {
        "evaluator": "no_show_charge_valid",
        "parameters": {"maximum_pickup_distance_m": 150, "minimum_wait_seconds": 300},
        "allowed_outcome": {"action": "NO_ACTION"},
    },
    "NS-003": {
        "evaluator": "no_show_driver_outside_pickup_radius",
        "parameters": {"fee_item": "cancellation_fee"},
        "allowed_outcome": {"action": "REFUND_DISPUTED_FEE_FULL"},
    },
    "NS-004": {
        "evaluator": "no_show_wait_too_short",
        "parameters": {"fee_item": "cancellation_fee"},
        "allowed_outcome": {"action": "REFUND_DISPUTED_FEE_FULL"},
    },
    "NS-005": {
        "evaluator": "no_show_no_platform_contact",
        "parameters": {"fee_item": "cancellation_fee"},
        "allowed_outcome": {"action": "REFUND_DISPUTED_FEE_FULL"},
    },
    "NS-006": {
        "evaluator": "no_show_authoritative_conflict",
        "parameters": {"maximum_time_conflict_seconds": 60, "maximum_position_conflict_m": 100},
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
    "NS-007": {
        "evaluator": "no_show_contact_coverage_incomplete",
        "parameters": {},
        "allowed_outcome": {"business_status": "PENDING_HUMAN_REVIEW"},
    },
}


def validate_policy_contract(policy: PolicyFile) -> None:
    ids = [rule["rule_id"] for rule in policy.rules]
    if len(ids) != len(set(ids)):
        raise ValueError("policy rule IDs must be unique")
    if not ids or any(not rule_id.startswith(("RD-", "NS-")) for rule_id in ids):
        raise ValueError("policy JSON may contain only RD/NS business rules")
    if set(ids) != set(EXPECTED_RULE_CONTRACTS):
        raise ValueError("policy rule set does not match implemented evaluators")
    for rule in policy.rules:
        expected = EXPECTED_RULE_CONTRACTS[rule["rule_id"]]
        for field in ("evaluator", "parameters", "allowed_outcome"):
            if rule.get(field) != expected[field]:
                raise ValueError(f"{rule['rule_id']} {field} conflicts with implemented evaluator contract")


def load_policy(path: str | Path) -> PolicyFile:
    policy = PolicyFile.model_validate_json(Path(path).read_text(encoding="utf-8"))
    validate_policy_contract(policy)
    return policy


def _snapshot_evidence(snapshot: CaseSnapshot, evidence_by_id: dict[str, Evidence]) -> list[Evidence]:
    result: list[Evidence] = []
    for evidence_id in snapshot.evidence_refs:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None:
            continue
        if evidence.origin_case_id == snapshot.case_id:
            result.append(evidence)
    return result


def _by_source(items: list[Evidence], source_type: SourceType) -> list[Evidence]:
    return [item for item in items if item.source_type == source_type]


def _canonical_payload(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _unique_authoritative_ledger(
    snapshot: CaseSnapshot,
    items: list[Evidence],
) -> tuple[Evidence | None, bool]:
    ledgers = [
        item
        for item in _by_source(items, SourceType.FARE_LEDGER)
        if item.trust_tier == TrustTier.AUTHORITATIVE and item.evidence_id in snapshot.evidence_refs
    ]
    if not ledgers:
        return None, False
    unique_payloads = {_canonical_payload(ledger.payload) for ledger in ledgers}
    if len(unique_payloads) > 1:
        return None, True
    return sorted(ledgers, key=lambda item: (item.source_record_id, item.evidence_id))[0], False


def _ledger_amount(ledger: Evidence, fee_item: str, currency: str) -> int | None:
    if ledger.payload.get("currency") != currency:
        return None
    matching = [
        item
        for item in ledger.payload.get("line_items", [])
        if item.get("fee_item") == fee_item
    ]
    if len(matching) != 1:
        return None
    amount = matching[0].get("amount_cents")
    return int(amount) if isinstance(amount, int) and amount >= 0 else None


def _pending(rule_id: str, reason: str, facts: dict[str, FactStatus] | None = None, metrics: dict[str, float] | None = None) -> PolicyEvaluation:
    return PolicyEvaluation(
        business_status=BusinessStatus.PENDING_HUMAN_REVIEW,
        matched_rule_ids=(rule_id,),
        allowed_action=None,
        facts=facts or {},
        metrics=metrics or {},
        review_reasons=(reason,),
    )


def _evaluate_route(snapshot: CaseSnapshot, items: list[Evidence], evidence_by_id: dict[str, Evidence], params: dict[str, Any]) -> PolicyEvaluation:
    ledger, ledger_conflict = _unique_authoritative_ledger(snapshot, items)
    if ledger_conflict:
        return _pending("GEN-005", "Conflicting authoritative fare ledgers")

    baselines = _by_source(items, SourceType.ROUTE_BASELINE)
    gps = aggregate_gps(snapshot, evidence_by_id)
    facts = {
        "FACT-GPS-COVERAGE-SUFFICIENT": FactStatus.PROVEN if gps.coverage_percent >= params["minimum_gps_coverage_percent"] else FactStatus.DISPROVEN,
        "FACT-ROUTE-BASELINE-PRESENT": FactStatus.PROVEN if len(baselines) == 1 else FactStatus.DISPROVEN,
        "FACT-FARE-LEDGER-PRESENT": FactStatus.PROVEN if ledger is not None else FactStatus.DISPROVEN,
    }
    metrics = {"gps_coverage_percent": gps.coverage_percent, "actual_distance_m": gps.actual_distance_m}
    if gps.conflict:
        return _pending("GEN-005", "; ".join(gps.conflict_reasons), facts, metrics)
    if gps.coverage_percent < params["minimum_gps_coverage_percent"] or len(baselines) != 1 or ledger is None:
        return _pending("RD-001", "Required route evidence is incomplete", facts, metrics)

    baseline_distance = float(baselines[0].payload.get("baseline_distance_m", 0))
    if baseline_distance <= 0:
        return _pending("RD-001", "Route baseline is invalid", facts, metrics)
    deviation_ratio = gps.actual_distance_m / baseline_distance
    metrics["deviation_ratio"] = deviation_ratio
    if deviation_ratio <= params["maximum_allowed_ratio"] + 1e-9:
        return PolicyEvaluation(
            business_status=BusinessStatus.RESOLVED,
            matched_rule_ids=("RD-002",),
            allowed_action=Action(type=ActionType.NO_ACTION, fee_item=None, amount_cents=0, currency="SGD"),
            facts=facts,
            metrics=metrics,
        )

    statements = _by_source(items, SourceType.PARTY_STATEMENT)
    if any(statement.payload.get("claims_oral_stop_request") is True for statement in statements):
        return _pending("RD-006", "An oral stop request was claimed but cannot be verified", facts, metrics)

    chats = _by_source(items, SourceType.AUTHENTICATED_CHAT)
    traffic = _by_source(items, SourceType.DEMO_TRAFFIC_FEED)
    chat_complete = len(chats) == 1 and chats[0].coverage is not None and chats[0].coverage.is_complete
    traffic_complete = len(traffic) == 1 and traffic[0].coverage is not None and traffic[0].coverage.is_complete
    requested_stop = any(
        message.get("tag") == "REQUESTED_STOP"
        for chat in chats
        for message in chat.payload.get("messages", [])
    )
    road_closure = any(
        event.get("type") == "ROAD_CLOSURE" and event.get("relevant") is True
        for feed in traffic
        for event in feed.payload.get("events", [])
    )
    if requested_stop or road_closure:
        return PolicyEvaluation(
            business_status=BusinessStatus.RESOLVED,
            matched_rule_ids=("RD-003",),
            allowed_action=Action(type=ActionType.NO_ACTION, fee_item=None, amount_cents=0, currency="SGD"),
            facts=facts,
            metrics=metrics,
        )
    if not chat_complete or not traffic_complete:
        return _pending("RD-005", "Exception-channel evidence is incomplete", facts, metrics)

    amount = _ledger_amount(ledger, "distance_surcharge", snapshot.currency)
    if amount is None or amount <= 0:
        return _pending("RD-005", "Refundable distance surcharge is unavailable", facts, metrics)
    return PolicyEvaluation(
        business_status=BusinessStatus.RESOLVED,
        matched_rule_ids=("RD-004",),
        allowed_action=Action(
            type=ActionType.REFUND_DISPUTED_FEE_FULL,
            fee_item="distance_surcharge",
            amount_cents=amount,
            currency="SGD",
        ),
        facts=facts,
        metrics=metrics,
    )


def _evaluate_no_show(snapshot: CaseSnapshot, items: list[Evidence], params: dict[str, Any]) -> PolicyEvaluation:
    ledger, ledger_conflict = _unique_authoritative_ledger(snapshot, items)
    if ledger_conflict:
        return _pending("GEN-005", "Conflicting authoritative fare ledgers")
    gps = [item for item in _by_source(items, SourceType.PLATFORM_GPS) if item.trust_tier == TrustTier.AUTHORITATIVE]
    events = [item for item in _by_source(items, SourceType.TRIP_EVENT_LOG) if item.trust_tier == TrustTier.AUTHORITATIVE]
    contacts = [item for item in _by_source(items, SourceType.CONTACT_LOG) if item.trust_tier == TrustTier.AUTHORITATIVE]
    if ledger is None or len(gps) != 1 or len(events) != 1 or len(contacts) != 1:
        return _pending("NS-001", "Required authoritative no-show evidence is incomplete")

    try:
        distance_m = float(gps[0].payload["arrival_distance_m"])
        arrived_at = datetime.fromisoformat(events[0].payload["arrived_at"])
        cancelled_at = datetime.fromisoformat(events[0].payload["cancelled_at"])
    except (KeyError, TypeError, ValueError):
        return _pending("NS-001", "Authoritative no-show evidence has an invalid payload")
    if (
        distance_m < 0
        or arrived_at.tzinfo is None
        or cancelled_at.tzinfo is None
        or not (snapshot.trip_started_at <= arrived_at < cancelled_at <= snapshot.trip_ended_at)
    ):
        return _pending("NS-001", "Authoritative no-show event interval is invalid")

    wait_seconds = (cancelled_at - arrived_at).total_seconds()
    contact_coverage = contacts[0].coverage
    contact_complete = (
        contact_coverage is not None
        and contact_coverage.is_complete
        and contact_coverage.start_at.tzinfo is not None
        and contact_coverage.end_at.tzinfo is not None
        and contact_coverage.start_at <= arrived_at
        and contact_coverage.end_at >= cancelled_at
    )
    attempts = contacts[0].payload.get("attempts", [])
    if not isinstance(attempts, list):
        return _pending("NS-001", "Authoritative contact log has an invalid payload")
    valid_attempts: list[dict[str, Any]] = []
    for attempt in attempts:
        if not isinstance(attempt, dict) or not isinstance(attempt.get("at"), str):
            return _pending("NS-001", "Authoritative contact log has an invalid attempt")
        try:
            attempted_at = datetime.fromisoformat(attempt["at"])
        except ValueError:
            return _pending("NS-001", "Authoritative contact log has an invalid attempt time")
        if attempted_at.tzinfo is None:
            return _pending("NS-001", "Authoritative contact attempt time must include a timezone")
        if attempt.get("channel") == "IN_APP" and arrived_at <= attempted_at <= cancelled_at:
            valid_attempts.append(attempt)
    metrics = {"arrival_distance_m": distance_m, "wait_seconds": wait_seconds}
    amount = _ledger_amount(ledger, "cancellation_fee", snapshot.currency)
    if amount is None:
        return _pending("NS-001", "Cancellation fee is unavailable", metrics=metrics)
    refund = Action(
        type=ActionType.REFUND_DISPUTED_FEE_FULL,
        fee_item="cancellation_fee",
        amount_cents=amount,
        currency="SGD",
    )
    if distance_m > params["maximum_pickup_distance_m"]:
        return PolicyEvaluation(business_status=BusinessStatus.RESOLVED, matched_rule_ids=("NS-003",), allowed_action=refund, metrics=metrics)
    if wait_seconds < params["minimum_wait_seconds"]:
        return PolicyEvaluation(business_status=BusinessStatus.RESOLVED, matched_rule_ids=("NS-004",), allowed_action=refund, metrics=metrics)
    if not contact_complete:
        return _pending("NS-007", "Contact-log coverage is incomplete", metrics=metrics)
    if not valid_attempts:
        return PolicyEvaluation(business_status=BusinessStatus.RESOLVED, matched_rule_ids=("NS-005",), allowed_action=refund, metrics=metrics)
    return PolicyEvaluation(
        business_status=BusinessStatus.RESOLVED,
        matched_rule_ids=("NS-002",),
        allowed_action=Action(type=ActionType.NO_ACTION, fee_item=None, amount_cents=0, currency="SGD"),
        metrics=metrics,
    )


def evaluate_case(snapshot: CaseSnapshot, evidence: list[Evidence], policy: PolicyFile) -> PolicyEvaluation:
    validate_policy_contract(policy)
    evidence_by_id = index_evidence(evidence)
    input_fingerprint = compute_input_fingerprint(snapshot, evidence_by_id, policy)

    def with_fingerprint(result: PolicyEvaluation) -> PolicyEvaluation:
        payload = result.model_dump(mode="python")
        payload["input_fingerprint"] = input_fingerprint
        return PolicyEvaluation.model_validate(payload)

    if snapshot.policy_version != policy.policy_version:
        return with_fingerprint(_pending("GEN-007", "Snapshot policy version does not match loaded policy"))
    trip_time = snapshot.trip_started_at.astimezone(timezone.utc)
    effective_from = datetime.fromisoformat(policy.effective_from).astimezone(timezone.utc)
    effective_to = datetime.fromisoformat(policy.effective_to).astimezone(timezone.utc) if policy.effective_to else None
    if trip_time < effective_from or (effective_to is not None and trip_time >= effective_to):
        return with_fingerprint(_pending("GEN-007", "No loaded policy version covers the trip start time"))
    items = _snapshot_evidence(snapshot, evidence_by_id)
    rules = {rule["rule_id"]: rule for rule in policy.rules}
    if snapshot.dispute_type == DisputeType.ROUTE_DEVIATION:
        params = dict(rules["RD-001"]["parameters"])
        params["maximum_allowed_ratio"] = rules["RD-002"]["parameters"]["maximum_allowed_ratio"]
        return with_fingerprint(_evaluate_route(snapshot, items, evidence_by_id, params))
    params = dict(rules["NS-002"]["parameters"])
    return with_fingerprint(_evaluate_no_show(snapshot, items, params))


def validate_judge_recommendation(
    evaluation: PolicyEvaluation,
    recommendation: JudgeRecommendation,
) -> None:
    if recommendation.recommended_case_status != evaluation.business_status:
        raise OutputIntegrityError("Judge status conflicts with deterministic policy evaluation")
    if recommendation.recommended_action != evaluation.allowed_action:
        raise OutputIntegrityError("Judge action conflicts with deterministic policy evaluation")
