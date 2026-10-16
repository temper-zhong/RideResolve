from __future__ import annotations

import json
from typing import Any

from rideresolve.case_store import CaseStore
from rideresolve.models import ActionType, BusinessStatus, SourceType
from rideresolve.policy import evaluate_case


CASE_ID = "CASE-NS-TOOL-001"
CASE_VERSION = 1
EXPECTED_RULE_ID = "NS-002"
REQUIRED_SOURCE_TYPES = {
    SourceType.PLATFORM_GPS,
    SourceType.TRIP_EVENT_LOG,
    SourceType.CONTACT_LOG,
    SourceType.FARE_LEDGER,
}


def build_readiness_report() -> dict[str, Any]:
    """Evaluate the persisted No-Show fixture without issuing live credentials."""
    store = CaseStore.load_default()
    snapshot = store.get_snapshot(CASE_ID, CASE_VERSION)
    evidence = store.get_evidence(snapshot)
    policy = store.get_policy(snapshot.policy_version)
    evaluation = evaluate_case(snapshot, evidence, policy)
    source_types = {item.source_type for item in evidence}
    action = evaluation.allowed_action

    checks = {
        "synthetic_dataset": store.synthetic,
        "required_sources_present": REQUIRED_SOURCE_TYPES.issubset(source_types),
        "deterministic_status_resolved": evaluation.business_status
        == BusinessStatus.RESOLVED,
        "expected_rule_matched": evaluation.matched_rule_ids == (EXPECTED_RULE_ID,),
        "expected_no_action": action is not None
        and action.type == ActionType.NO_ACTION
        and action.fee_item is None
        and action.amount_cents == 0,
    }
    return {
        "ready": all(checks.values()),
        "purpose": "NO_SHOW_REAL_ADP_RUN_READINESS",
        "credentials_issued": False,
        "dataset_id": store.dataset_id,
        "case_id": snapshot.case_id,
        "case_version": snapshot.case_version,
        "policy_version": snapshot.policy_version,
        "checks": checks,
        "expected_deterministic_result": {
            "business_status": evaluation.business_status.value,
            "matched_rule_ids": list(evaluation.matched_rule_ids),
            "allowed_action": (
                action.model_dump(mode="json") if action is not None else None
            ),
            "input_fingerprint": evaluation.input_fingerprint,
        },
        "evidence_ids": [item.evidence_id for item in evidence],
        "source_types": sorted(item.value for item in source_types),
    }


def main() -> None:
    report = build_readiness_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    raise SystemExit(0 if report["ready"] else 1)


if __name__ == "__main__":
    main()
