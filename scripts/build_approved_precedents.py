from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from rideresolve.learning_feedback import capture_reviewer_correction
from rideresolve.models import Action, ActionType, BusinessStatus, DisputeType


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "feedback" / "approved_precedents.json"


def refund(fee_item: str, amount_cents: int) -> Action:
    return Action(
        type=ActionType.REFUND_DISPUTED_FEE_FULL,
        fee_item=fee_item,
        amount_cents=amount_cents,
        currency="SGD",
    )


def no_action() -> Action:
    return Action(
        type=ActionType.NO_ACTION,
        fee_item=None,
        amount_cents=0,
        currency="SGD",
    )


def build_records():
    common = {
        "policy_version": "DEMO_POLICY_V1",
        "reviewer_role": "HUMAN_REVIEWER",
        "synthetic": True,
        "publication_status": "APPROVED_FOR_PRECEDENT",
        "learning_scope": "ADVISORY_PRECEDENT_ONLY",
    }
    return [
        capture_reviewer_correction(
            **common,
            feedback_id="FB-RD-004-001",
            source_case_id="CASE-RD-HIST-042",
            source_case_version=2,
            dispute_type=DisputeType.ROUTE_DEVIATION,
            reviewed_at=datetime(2026, 10, 8, 10, 30, tzinfo=timezone.utc),
            original_status=BusinessStatus.RESOLVED,
            original_action=refund("distance_surcharge", 325),
            corrected_status=BusinessStatus.PENDING_HUMAN_REVIEW,
            corrected_action=None,
            source_rule_ids=("RD-004",),
            evidence_citations=(
                "HIST-EV-RD-042-LEDGER-A",
                "HIST-EV-RD-042-LEDGER-LATE",
            ),
            correction_reason=(
                "A second authoritative fare ledger arrived after the original review and "
                "conflicted with the amount basis, so the case required reconciliation "
                "instead of automatic refund."
            ),
        ),
        capture_reviewer_correction(
            **common,
            feedback_id="FB-RD-004-002",
            source_case_id="CASE-RD-HIST-087",
            source_case_version=1,
            dispute_type=DisputeType.ROUTE_DEVIATION,
            reviewed_at=datetime(2026, 10, 9, 3, 20, tzinfo=timezone.utc),
            original_status=BusinessStatus.RESOLVED,
            original_action=refund("distance_surcharge", 510),
            corrected_status=BusinessStatus.PENDING_HUMAN_REVIEW,
            corrected_action=None,
            source_rule_ids=("RD-004",),
            evidence_citations=(
                "HIST-EV-RD-087-GPS",
                "HIST-EV-RD-087-BASELINE-CORRECTION",
            ),
            correction_reason=(
                "A reviewer found that a corrected route baseline materially changed the "
                "distance ratio, so the automatic refund was withdrawn pending reconciliation."
            ),
        ),
        capture_reviewer_correction(
            **common,
            feedback_id="FB-NS-005-001",
            source_case_id="CASE-NS-HIST-019",
            source_case_version=1,
            dispute_type=DisputeType.NO_SHOW,
            reviewed_at=datetime(2026, 10, 9, 14, 5, tzinfo=timezone.utc),
            original_status=BusinessStatus.RESOLVED,
            original_action=no_action(),
            corrected_status=BusinessStatus.RESOLVED,
            corrected_action=refund("cancellation_fee", 465),
            source_rule_ids=("NS-005",),
            evidence_citations=(
                "HIST-EV-NS-019-CONTACT",
                "HIST-EV-NS-019-LEDGER",
            ),
            correction_reason=(
                "The approved contact export proved that no in-app attempt occurred during "
                "the complete waiting interval, so the cancellation fee was refunded."
            ),
        ),
        capture_reviewer_correction(
            **common,
            feedback_id="FB-NS-003-POLICY-CONFLICT-001",
            source_case_id="CASE-NS-HIST-061",
            source_case_version=3,
            dispute_type=DisputeType.NO_SHOW,
            reviewed_at=datetime(2026, 10, 10, 1, 40, tzinfo=timezone.utc),
            original_status=BusinessStatus.RESOLVED,
            original_action=refund("cancellation_fee", 340),
            corrected_status=BusinessStatus.RESOLVED,
            corrected_action=no_action(),
            source_rule_ids=("NS-003",),
            evidence_citations=(
                "HIST-EV-NS-061-GPS",
                "HIST-EV-NS-061-PICKUP-ZONE-NOTICE",
            ),
            correction_reason=(
                "A historical reviewer accepted a temporary staging-zone exception and kept "
                "the fee; that exception is absent from the current policy and is advisory only."
            ),
        ),
    ]


def main() -> None:
    records = build_records()
    payload = {
        "knowledge_base_id": "RIDERESOLVE_PRECEDENT_MEMORY_V1",
        "synthetic": True,
        "records": [record.model_dump(mode="json") for record in records],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
