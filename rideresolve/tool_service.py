from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .case_store import CaseStore
from .gps import aggregate_gps
from .integrity import evidence_checksum_is_valid, index_evidence
from .models import DisputeType, Evidence, SourceType


class ToolRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CaseSnapshotRequest(ToolRequest):
    pass


class TripEvidenceRequest(ToolRequest):
    evidence_types: list[SourceType] | None = Field(default=None, min_length=1, max_length=8)
    detail: Literal["SUMMARY", "FULL"] = "SUMMARY"


class PolicyRulesRequest(ToolRequest):
    rule_ids: list[str] | None = Field(default=None, min_length=1, max_length=20)


@dataclass(frozen=True)
class ToolScope:
    run_id: str
    actor_role: str
    case_id: str
    case_version: int
    policy_version: str


def _evidence_payload(item: Evidence, detail: str) -> dict[str, Any]:
    payload = item.payload
    if detail == "SUMMARY" and item.source_type == SourceType.PLATFORM_GPS and "samples" in payload:
        samples = payload.get("samples", [])
        payload = {
            "sample_count": len(samples),
            "first_sample_at": samples[0].get("timestamp") if samples else None,
            "last_sample_at": samples[-1].get("timestamp") if samples else None,
        }
    return {
        "evidence_id": item.evidence_id,
        "source_record_id": item.source_record_id,
        "source_type": item.source_type.value,
        "trust_tier": item.trust_tier.value,
        "observed_at": item.observed_at.isoformat(),
        "collected_at": item.collected_at.isoformat(),
        "coverage": item.coverage.model_dump(mode="json") if item.coverage else None,
        "record_role": item.record_role.value,
        "related_evidence_ids": list(item.related_evidence_ids),
        "provenance_reason": item.provenance_reason,
        "payload": payload,
        "checksum_verified": evidence_checksum_is_valid(item),
    }


class ToolService:
    def __init__(self, store: CaseStore) -> None:
        self.store = store

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
                    "conflict": gps.conflict,
                    "conflict_reasons": list(gps.conflict_reasons),
                }
        return response

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
            "policy_id": policy.policy_id,
            "policy_version": policy.policy_version,
            "effective_from": policy.effective_from,
            "effective_to": policy.effective_to,
            "timezone": policy.timezone,
            "rules": rules,
        }
