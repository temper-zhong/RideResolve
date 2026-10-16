from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .case_store import CaseStore
from .gps import aggregate_gps
from .integrity import evidence_checksum_is_valid, index_evidence
from .learning_feedback import (
    PrecedentKnowledgeBase,
    retrieve_approved_precedents,
)
from .models import DisputeType, Evidence, JudgeRecommendation, SourceType
from .policy import OutputIntegrityError, evaluate_case, validate_judge_recommendation


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseSnapshotRequest(ToolRequest):
    pass


class TripEvidenceRequest(ToolRequest):
    evidence_types: list[SourceType] | None = Field(default=None, min_length=1, max_length=12)
    detail: Literal["DECISION_FACTS", "SUMMARY", "FULL"] = "DECISION_FACTS"


class PolicyRulesRequest(ToolRequest):
    # ADP is more reliable when a tool has one explicit, non-empty argument.
    # Keep a default so previously imported tool definitions that send `{}`
    # remain backward compatible with the deployed service.
    scope: Literal["APPLICABLE_DISPUTE"] = "APPLICABLE_DISPUTE"
    rule_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)


class PrecedentSearchRequest(ToolRequest):
    limit: int = Field(default=3, ge=1, le=3)


class DeterministicEvaluationRequest(ToolRequest):
    scope: Literal["LOCKED_RUN"] = "LOCKED_RUN"


class JudgeValidationRequest(ToolRequest):
    run_id: str = Field(min_length=1, max_length=128)
    recommendation: JudgeRecommendation

    @field_validator("recommendation", mode="before")
    @classmethod
    def parse_serialized_recommendation(cls, value: Any) -> Any:
        """Accept the ADP workflow transport form without weakening validation.

        ADP cannot pass a nested object containing JSON null reliably between a Code
        node and a custom API node. It therefore sends the exact Judge JSON as a
        string. Some ADP tool-client paths wrap that string one extra time while
        assembling a JSON request, so unwrap at most that single transport layer.
        The resulting value is still validated by the same strict
        JudgeRecommendation model used for direct API callers.
        """
        if not isinstance(value, str):
            return value
        serialized = value
        for _ in range(2):
            try:
                parsed = json.loads(serialized)
            except json.JSONDecodeError as exc:
                raise ValueError("recommendation must be valid JSON") from exc
            if isinstance(parsed, dict):
                return parsed
            if not isinstance(parsed, str):
                break
            serialized = parsed
        raise ValueError("recommendation JSON must decode to an object")


@dataclass(frozen=True)
class ToolScope:
    run_id: str
    actor_role: str
    case_id: str
    case_version: int
    policy_version: str


def _decision_fact_payload(item: Evidence) -> dict[str, Any]:
    """Return only policy-material fields while preserving their authoritative values."""
    payload = item.payload
    if item.source_type == SourceType.PLATFORM_GPS:
        samples = payload.get("samples", [])
        keys = ("reported_actual_distance_m", "arrival_distance_m", "official_evidence_complete")
        return {
            "sample_count": len(samples),
            "first_sample_at": samples[0].get("timestamp") if samples else None,
            "last_sample_at": samples[-1].get("timestamp") if samples else None,
            **{key: payload[key] for key in keys if key in payload},
        }
    if item.source_type == SourceType.ROUTE_BASELINE:
        keys = ("baseline_distance_m", "estimated_duration_min")
        return {key: payload[key] for key in keys if key in payload}
    if item.source_type == SourceType.FARE_LEDGER:
        keys = (
            "currency",
            "line_items",
            "total_paid_cents",
            "estimated_total_cents",
            "actual_total_cents",
        )
        return {key: payload[key] for key in keys if key in payload}
    if item.source_type == SourceType.AUTHENTICATED_CHAT:
        keys = (
            "route_notification_sent",
            "verbal_notification_verified",
            "rider_inquired_about_route",
        )
        result = {key: payload[key] for key in keys if key in payload}
        if not result and "messages" in payload:
            result["messages"] = [
                {
                    key: message[key]
                    for key in ("message_id", "tag", "sender", "at", "timestamp")
                    if key in message
                }
                for message in payload["messages"]
            ]
        return result
    if item.source_type == SourceType.DEMO_TRAFFIC_FEED:
        keys = ("reroute_justified", "notification_failure")
        result = {key: payload[key] for key in keys if key in payload}
        result["events"] = [
            {
                key: event[key]
                for key in ("incident_id", "type", "incident_type", "relevant", "severity")
                if key in event
            }
            for event in payload.get("events", [])
        ]
        return result
    if item.source_type == SourceType.TRIP_EVENT_LOG:
        keys = ("scheduled_at", "arrived_at", "cancelled_at", "cancelled_by")
        return {key: payload[key] for key in keys if key in payload}
    if item.source_type == SourceType.CONTACT_LOG:
        return {
            "attempts": [
                {
                    key: attempt[key]
                    for key in ("channel", "at", "timestamp", "outcome")
                    if key in attempt
                }
                for attempt in payload.get("attempts", [])
            ]
        }
    if item.source_type == SourceType.PARTY_STATEMENT:
        return {
            "claims_oral_stop_request": payload.get("claims_oral_stop_request", False)
        }
    if item.source_type == SourceType.SURGE_PRICING_LOG:
        keys = ("quote_time_surge", "trip_start_surge")
        return {key: payload[key] for key in keys if key in payload}
    if item.source_type == SourceType.NOTIFICATION_LOG:
        return {"rider_notified": payload.get("rider_notified")}
    if item.source_type == SourceType.HISTORICAL_BEHAVIOR_PROFILE:
        return {"decision_use": "EXCLUDED_FROM_ADJUDICATION"}
    return {}


def _evidence_payload(item: Evidence, detail: str) -> dict[str, Any]:
    payload = item.payload
    if detail == "DECISION_FACTS":
        payload = _decision_fact_payload(item)
    elif detail == "SUMMARY" and item.source_type == SourceType.PLATFORM_GPS and "samples" in payload:
        samples = payload.get("samples", [])
        payload = {
            "sample_count": len(samples),
            "first_sample_at": samples[0].get("timestamp") if samples else None,
            "last_sample_at": samples[-1].get("timestamp") if samples else None,
            **(
                {"reported_actual_distance_m": payload["reported_actual_distance_m"]}
                if "reported_actual_distance_m" in payload
                else {}
            ),
            **(
                {"arrival_distance_m": payload["arrival_distance_m"]}
                if "arrival_distance_m" in payload
                else {}
            ),
        }
    result = {
        "evidence_id": item.evidence_id,
        "source_type": item.source_type.value,
        "trust_tier": item.trust_tier.value,
        "coverage": item.coverage.model_dump(mode="json") if item.coverage else None,
        "record_role": item.record_role.value,
        "payload": payload,
        "checksum_verified": evidence_checksum_is_valid(item),
    }
    if detail != "DECISION_FACTS":
        result.update(
            {
                "source_record_id": item.source_record_id,
                "observed_at": item.observed_at.isoformat(),
                "collected_at": item.collected_at.isoformat(),
                "related_evidence_ids": list(item.related_evidence_ids),
                "provenance_reason": item.provenance_reason,
            }
        )
    return result


class ToolService:
    def __init__(
        self,
        store: CaseStore,
        precedent_knowledge_base: PrecedentKnowledgeBase | None = None,
    ) -> None:
        self.store = store
        self.precedent_knowledge_base = (
            precedent_knowledge_base or PrecedentKnowledgeBase.load_default()
        )

    @classmethod
    def load_default(cls) -> "ToolService":
        return cls(CaseStore.load_default())

    def get_case_snapshot(self, scope: ToolScope, request: CaseSnapshotRequest) -> dict[str, Any]:
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        available = self.store.get_evidence(snapshot)
        case_payload = snapshot.model_dump(mode="json")
        evidence_reference_count = len(case_payload.pop("evidence_refs"))
        return {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "dataset_id": self.store.dataset_id,
            "synthetic": self.store.synthetic,
            "case_origin": self.store.case_origin(snapshot),
            "case": case_payload,
            "evidence_reference_count": evidence_reference_count,
            "available_evidence_types": sorted({item.source_type.value for item in available}),
        }

    def get_trip_evidence(self, scope: ToolScope, request: TripEvidenceRequest) -> dict[str, Any]:
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        filters = set(request.evidence_types) if request.evidence_types else None
        selected = self.store.get_evidence(snapshot, filters)
        response: dict[str, Any] = {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "dataset_id": self.store.dataset_id,
            "synthetic": self.store.synthetic,
            "case_origin": self.store.case_origin(snapshot),
            "case_id": snapshot.case_id,
            "case_version": snapshot.case_version,
            "detail": request.detail,
            "evidence": [_evidence_payload(item, request.detail) for item in selected],
        }
        if filters is None or SourceType.PLATFORM_GPS in filters:
            all_items = self.store.get_evidence(snapshot)
            if any(item.source_type == SourceType.PLATFORM_GPS and "samples" in item.payload for item in all_items):
                gps = aggregate_gps(snapshot, index_evidence(all_items))
                response["gps_aggregate"] = {
                    "coverage_percent": round(gps.coverage_percent, 6),
                    "actual_distance_m": round(gps.actual_distance_m, 3),
                    "unique_sample_count": gps.unique_sample_count,
                    "conflict": gps.conflict,
                    "conflict_reasons": list(gps.conflict_reasons),
                }
        return response

    @staticmethod
    def _decision_evidence_ids(items: list[Evidence]) -> list[str]:
        return [
            item.evidence_id
            for item in items
            if item.source_type != SourceType.HISTORICAL_BEHAVIOR_PROFILE
        ]

    @staticmethod
    def _concise_message(evaluation: Any) -> str:
        rules = ", ".join(evaluation.matched_rule_ids)
        if evaluation.allowed_action is None:
            reason = evaluation.review_reasons[0] if evaluation.review_reasons else "Policy requires human review."
            outcome = f"Human review required; no automated adjustment. Reason: {reason}"
        elif evaluation.allowed_action.type.value == "NO_ACTION":
            outcome = "No refund or fee adjustment is recommended."
        else:
            action = evaluation.allowed_action
            amount = f"{action.currency} {action.amount_cents / 100:.2f}"
            qualifier = "partially refund" if action.type.value.endswith("PARTIAL") else "refund"
            outcome = f"Recommend to {qualifier} {amount} for {action.fee_item}."
        return (
            f"{outcome} Policy: {rules}. "
            "Synthetic recommendation only; no refund, fee adjustment, or notification was executed."
        )

    def get_deterministic_evaluation(
        self,
        scope: ToolScope,
        request: DeterministicEvaluationRequest,
    ) -> dict[str, Any]:
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        evidence = self.store.get_evidence(snapshot)
        policy = self.store.get_policy(scope.policy_version)
        evaluation = evaluate_case(snapshot, evidence, policy)
        return {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "dataset_id": self.store.dataset_id,
            "synthetic": self.store.synthetic,
            "case_origin": self.store.case_origin(snapshot),
            "case_id": snapshot.case_id,
            "case_version": snapshot.case_version,
            "dispute_type": snapshot.dispute_type.value,
            "policy_version": snapshot.policy_version,
            "data_precedence": "OFFICIAL_OVER_LEGACY_MOCK",
            "decision_evidence_ids": self._decision_evidence_ids(evidence),
            "evaluation": evaluation.model_dump(mode="json"),
            "message": self._concise_message(evaluation),
        }

    def validate_recommendation(
        self,
        scope: ToolScope,
        request: JudgeValidationRequest,
    ) -> dict[str, Any]:
        if request.run_id != scope.run_id:
            raise OutputIntegrityError("Judge run_id conflicts with the locked run")
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        evidence = self.store.get_evidence(snapshot)
        policy = self.store.get_policy(scope.policy_version)
        evaluation = evaluate_case(snapshot, evidence, policy)
        recommendation = request.recommendation
        valid_evidence_ids = set(self._decision_evidence_ids(evidence))
        cited_evidence_ids = set(recommendation.evidence_citations)
        if (
            not cited_evidence_ids
            or len(cited_evidence_ids) != len(recommendation.evidence_citations)
            or not cited_evidence_ids.issubset(valid_evidence_ids)
        ):
            raise OutputIntegrityError("Judge evidence citations conflict with the locked evidence")
        if recommendation.policy_citations != evaluation.matched_rule_ids:
            raise OutputIntegrityError("Judge policy citations conflict with deterministic policy evaluation")
        validate_judge_recommendation(evaluation, recommendation)
        return {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "dataset_id": self.store.dataset_id,
            "synthetic": self.store.synthetic,
            "case_origin": self.store.case_origin(snapshot),
            "case_id": snapshot.case_id,
            "case_version": snapshot.case_version,
            "policy_version": snapshot.policy_version,
            "validation_status": "PASSED",
            "validated_by": "PYTHON_DETERMINISTIC_GATE",
            "message": self._concise_message(evaluation),
            "recommendation": recommendation.model_dump(mode="json"),
            "authoritative_evaluation": evaluation.model_dump(mode="json"),
        }

    def get_policy_rules(self, scope: ToolScope, request: PolicyRulesRequest) -> dict[str, Any]:
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        policy = self.store.get_policy(scope.policy_version)
        rules = [
            rule
            for rule in policy.rules
            if rule["dispute_type"] == snapshot.dispute_type.value
        ]
        if request.rule_ids is not None:
            requested = set(request.rule_ids)
            rules = [rule for rule in rules if rule["rule_id"] in requested]
        return {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "case_origin": self.store.case_origin(snapshot),
            "case_id": snapshot.case_id,
            "case_version": snapshot.case_version,
            "dispute_type": snapshot.dispute_type.value,
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "effective_from": policy.effective_from,
            "effective_to": policy.effective_to,
            "timezone": policy.timezone,
            "rules": rules,
            "policy_precedents": list(policy.precedents),
        }

    def search_precedents(
        self,
        scope: ToolScope,
        request: PrecedentSearchRequest,
    ) -> dict[str, Any]:
        """Search only approved precedents using server-derived case and rule context."""
        snapshot = self.store.get_snapshot(scope.case_id, scope.case_version)
        evidence = self.store.get_evidence(snapshot)
        policy = self.store.get_policy(scope.policy_version)
        evaluation = evaluate_case(snapshot, evidence, policy)
        rule_ids = tuple(evaluation.matched_rule_ids)
        matches, advisory = retrieve_approved_precedents(
            dispute_type=snapshot.dispute_type,
            policy_version=snapshot.policy_version,
            rule_ids=rule_ids,
            knowledge_base=self.precedent_knowledge_base,
            limit=request.limit,
        )
        return {
            "run_id": scope.run_id,
            "tool_actor_role": scope.actor_role,
            "dataset_id": self.store.dataset_id,
            "synthetic": self.store.synthetic,
            "knowledge_base_id": self.precedent_knowledge_base.knowledge_base_id,
            "authority": "ADVISORY_ONLY",
            "may_override_policy": False,
            "query_context": {
                "case_id": snapshot.case_id,
                "case_version": snapshot.case_version,
                "dispute_type": snapshot.dispute_type.value,
                "policy_version": snapshot.policy_version,
                "matched_rule_ids": list(rule_ids),
            },
            "matches": [
                {
                    "precedent_id": item.feedback_id,
                    "similarity_score": item.similarity_score,
                    "source_case_id": item.source_case_id,
                    "source_rule_ids": list(item.source_rule_ids),
                    "corrected_status": item.corrected_status.value,
                    "corrected_action": (
                        item.corrected_action.model_dump(mode="json")
                        if item.corrected_action is not None
                        else None
                    ),
                    "correction_reason": item.correction_reason,
                }
                for item in matches
            ],
            "advisory": advisory,
        }
