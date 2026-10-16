from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DisputeType(StrEnum):
    ROUTE_DEVIATION = "ROUTE_DEVIATION"
    NO_SHOW = "NO_SHOW"
    FARE_DISPUTE = "FARE_DISPUTE"


class SourceType(StrEnum):
    PLATFORM_GPS = "PLATFORM_GPS"
    FARE_LEDGER = "FARE_LEDGER"
    ROUTE_BASELINE = "ROUTE_BASELINE"
    TRIP_EVENT_LOG = "TRIP_EVENT_LOG"
    CONTACT_LOG = "CONTACT_LOG"
    AUTHENTICATED_CHAT = "AUTHENTICATED_CHAT"
    DEMO_TRAFFIC_FEED = "DEMO_TRAFFIC_FEED"
    PARTY_STATEMENT = "PARTY_STATEMENT"
    HISTORICAL_BEHAVIOR_PROFILE = "HISTORICAL_BEHAVIOR_PROFILE"
    SURGE_PRICING_LOG = "SURGE_PRICING_LOG"
    NOTIFICATION_LOG = "NOTIFICATION_LOG"


class TrustTier(StrEnum):
    AUTHORITATIVE = "AUTHORITATIVE"
    SUPPORTING = "SUPPORTING"
    CLAIM = "CLAIM"


class RecordRole(StrEnum):
    ORIGINAL = "ORIGINAL"
    SUPPLEMENT = "SUPPLEMENT"
    CORRECTION = "CORRECTION"


class BusinessStatus(StrEnum):
    RESOLVED = "RESOLVED"
    PENDING_HUMAN_REVIEW = "PENDING_HUMAN_REVIEW"


class ProcessingStatus(StrEnum):
    RUN_COMPLETED = "RUN_COMPLETED"
    RUN_FAILED = "RUN_FAILED"


class ActionType(StrEnum):
    NO_ACTION = "NO_ACTION"
    REFUND_DISPUTED_FEE_FULL = "REFUND_DISPUTED_FEE_FULL"
    REFUND_DISPUTED_FEE_PARTIAL = "REFUND_DISPUTED_FEE_PARTIAL"


class FactStatus(StrEnum):
    PROVEN = "PROVEN"
    PROVEN_ABSENT = "PROVEN_ABSENT"
    DISPROVEN = "DISPROVEN"
    NOT_OBSERVED = "NOT_OBSERVED"
    UNKNOWN = "UNKNOWN"
    CONFLICTED = "CONFLICTED"


class Coverage(FrozenModel):
    start_at: datetime
    end_at: datetime
    is_complete: bool
    scope: str


class CaseSnapshot(FrozenModel):
    case_id: str
    case_version: int = Field(ge=1)
    dispute_type: DisputeType
    policy_version: str
    currency: Literal["SGD"]
    trip_started_at: datetime
    trip_ended_at: datetime
    claim_text: str
    disputed_fee_item: str
    disputed_amount_cents: int = Field(ge=0)
    evidence_refs: tuple[str, ...]
    created_at: datetime

    @model_validator(mode="after")
    def validate_times_and_refs(self) -> "CaseSnapshot":
        if self.trip_ended_at <= self.trip_started_at:
            raise ValueError("trip_ended_at must be later than trip_started_at")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("evidence_refs must be unique")
        return self


class Evidence(FrozenModel):
    evidence_id: str
    origin_case_id: str
    source_record_id: str
    source_type: SourceType
    trust_tier: TrustTier
    observed_at: datetime
    collected_at: datetime
    coverage: Coverage | None = None
    record_role: RecordRole = RecordRole.ORIGINAL
    related_evidence_ids: tuple[str, ...] = ()
    provenance_reason: str
    payload: dict[str, Any]
    checksum: str


class Action(FrozenModel):
    type: ActionType
    fee_item: str | None
    amount_cents: int = Field(ge=0)
    currency: Literal["SGD"]

    @model_validator(mode="after")
    def validate_action(self) -> "Action":
        if self.type == ActionType.NO_ACTION:
            if self.fee_item is not None or self.amount_cents != 0:
                raise ValueError("NO_ACTION requires fee_item=null and amount_cents=0")
        elif not self.fee_item or self.amount_cents <= 0:
            raise ValueError("refund actions require a fee item and positive amount")
        return self


class PolicyEvaluation(FrozenModel):
    business_status: BusinessStatus
    matched_rule_ids: tuple[str, ...]
    allowed_action: Action | None
    evaluated_by: Literal["DETERMINISTIC_POLICY_CODE"] = "DETERMINISTIC_POLICY_CODE"
    facts: dict[str, FactStatus] = Field(default_factory=dict)
    metrics: dict[str, float] = Field(default_factory=dict)
    review_reasons: tuple[str, ...] = ()
    input_fingerprint: str = ""

    @model_validator(mode="after")
    def validate_status_action(self) -> "PolicyEvaluation":
        if self.business_status == BusinessStatus.RESOLVED and self.allowed_action is None:
            raise ValueError("RESOLVED requires an allowed_action")
        if self.business_status == BusinessStatus.PENDING_HUMAN_REVIEW and self.allowed_action is not None:
            raise ValueError("PENDING_HUMAN_REVIEW requires allowed_action=null")
        return self


class JudgeConfidence(FrozenModel):
    score: int = Field(ge=0, le=100)
    label: Literal["UNCALIBRATED_MODEL_SELF_ASSESSMENT"]
    rationale: str


class JudgeRecommendation(FrozenModel):
    recommended_case_status: BusinessStatus
    recommended_action: Action | None
    evidence_citations: tuple[str, ...]
    policy_citations: tuple[str, ...]
    judge_confidence: JudgeConfidence
    reasoning_summary: str
    uncertainties: tuple[str, ...] = ()
    rider_explanation: str
    driver_explanation: str

    @model_validator(mode="after")
    def validate_status_action(self) -> "JudgeRecommendation":
        if self.recommended_case_status == BusinessStatus.RESOLVED and self.recommended_action is None:
            raise ValueError("Judge RESOLVED recommendation requires an action")
        if self.recommended_case_status == BusinessStatus.PENDING_HUMAN_REVIEW and self.recommended_action is not None:
            raise ValueError("Judge pending-review recommendation requires action=null")
        return self


class DecisionDelta(FrozenModel):
    case_id: str
    from_version: int
    to_version: int
    policy_version: str
    comparable: bool
    not_comparable_reasons: tuple[str, ...]
    changed_evidence_id: str | None
    changed_fact_id: str | None
    changed_rule_ids: tuple[str, ...]
    business_status_before: BusinessStatus | None
    business_status_after: BusinessStatus | None
    action_before: Action | None
    action_after: Action | None
    refund_delta_cents: int
    judge_consistent_before: bool
    judge_consistent_after: bool
    causal_claim_allowed: bool
    display_message: str
