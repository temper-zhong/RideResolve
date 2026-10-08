from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import ValidationError

from rideresolve.delta import build_decision_delta
from rideresolve.gps import aggregate_gps, haversine_m
from rideresolve.integrity import EvidenceIntegrityError, compute_evidence_checksum
from rideresolve.models import (
    Action,
    ActionType,
    BusinessStatus,
    CaseSnapshot,
    Coverage,
    DisputeType,
    Evidence,
    JudgeConfidence,
    JudgeRecommendation,
    RecordRole,
    SourceType,
    TrustTier,
)
from rideresolve.policy import (
    OutputIntegrityError,
    evaluate_case,
    load_policy,
    validate_judge_recommendation,
)


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "data" / "policies" / "DEMO_POLICY_V1.json"
CASES_PATH = ROOT / "data" / "cases" / "gate_b_expected_cases.json"
SGT = timezone(timedelta(hours=8))
START = datetime(2026, 10, 6, 9, 0, tzinfo=SGT)
END = START + timedelta(minutes=10)


def coverage(complete: bool = True, scope: str = "trip") -> Coverage:
    return Coverage(start_at=START, end_at=END, is_complete=complete, scope=scope)


def evidence(
    evidence_id: str,
    case_id: str,
    source_type: SourceType,
    payload: dict,
    *,
    trust: TrustTier = TrustTier.AUTHORITATIVE,
    item_coverage: Coverage | None = None,
    role: RecordRole = RecordRole.ORIGINAL,
    related: tuple[str, ...] = (),
) -> Evidence:
    candidate = Evidence(
        evidence_id=evidence_id,
        origin_case_id=case_id,
        source_record_id=f"SRC-{evidence_id}",
        source_type=source_type,
        trust_tier=trust,
        observed_at=START,
        collected_at=END,
        coverage=item_coverage,
        record_role=role,
        related_evidence_ids=related,
        provenance_reason="Synthetic Gate B fixture",
        payload=payload,
        checksum="",
    )
    return candidate.model_copy(update={"checksum": compute_evidence_checksum(candidate)})


def all_samples() -> list[dict]:
    return [
        {
            "timestamp": (START + timedelta(seconds=60 * index)).isoformat(),
            "latitude": 1.3000,
            "longitude": 103.8000 + 0.0100 * index,
        }
        for index in range(11)
    ]


def total_sample_distance(samples: list[dict]) -> float:
    return sum(
        haversine_m(
            left["latitude"],
            left["longitude"],
            right["latitude"],
            right["longitude"],
        )
        for left, right in zip(samples, samples[1:])
    )


def make_route_fixture(case_key: str, *, version: int = 1, supplement: bool = False):
    case_id = "CASE-RD-DELTA" if case_key == "RD_INCOMPLETE_GPS" else f"CASE-{case_key}"
    samples = all_samples()
    ratio = 1.2 if case_key == "RD_BOUNDARY_20_PERCENT" else 1.30
    baseline_distance = total_sample_distance(samples) / ratio

    items: list[Evidence] = []
    if case_key == "RD_INCOMPLETE_GPS":
        gps_a = evidence(
            "EV-GPS-A",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples[:3]},
            item_coverage=coverage(False, "trip-segment"),
        )
        gps_b = evidence(
            "EV-GPS-B",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples[5:]},
            item_coverage=coverage(False, "trip-segment"),
        )
        items.extend([gps_a, gps_b])
        if supplement:
            items.append(
                evidence(
                    "EV-GPS-SUPPLEMENT",
                    case_id,
                    SourceType.PLATFORM_GPS,
                    {"samples": samples[3:5]},
                    item_coverage=coverage(True, "missing-trip-segment"),
                    role=RecordRole.SUPPLEMENT,
                    related=("EV-GPS-A", "EV-GPS-B"),
                )
            )
    else:
        items.append(
            evidence(
                "EV-GPS-FULL",
                case_id,
                SourceType.PLATFORM_GPS,
                {"samples": samples},
                item_coverage=coverage(),
            )
        )

    items.extend(
        [
            evidence(
                "EV-BASELINE",
                case_id,
                SourceType.ROUTE_BASELINE,
                {"baseline_distance_m": baseline_distance},
            ),
            evidence(
                "EV-FARE",
                case_id,
                SourceType.FARE_LEDGER,
                {
                    "currency": "SGD",
                    "line_items": [{"fee_item": "distance_surcharge", "amount_cents": 325}],
                    "total_paid_cents": 2480,
                },
            ),
            evidence(
                "EV-CHAT",
                case_id,
                SourceType.AUTHENTICATED_CHAT,
                {"messages": []},
                trust=TrustTier.SUPPORTING,
                item_coverage=coverage(True, "platform-trip-chat"),
            ),
            evidence(
                "EV-TRAFFIC",
                case_id,
                SourceType.DEMO_TRAFFIC_FEED,
                {
                    "events": [
                        {"type": "ROAD_CLOSURE", "relevant": True}
                    ] if case_key == "RD_VERIFIED_ROAD_CLOSURE" else []
                },
                trust=TrustTier.SUPPORTING,
                item_coverage=coverage(True, "trip-corridor"),
            ),
        ]
    )
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=version,
        dispute_type=DisputeType.ROUTE_DEVIATION,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=START,
        trip_ended_at=END,
        claim_text="The driver took a longer route and I was overcharged.",
        disputed_fee_item="distance_surcharge",
        disputed_amount_cents=325,
        evidence_refs=tuple(item.evidence_id for item in items),
        created_at=END + timedelta(minutes=version),
    )
    return snapshot, items


def make_no_show_fixture(case_key: str):
    case_id = f"CASE-{case_key}"
    distance_m = 300 if case_key == "NS_DRIVER_TOO_FAR" else 100
    wait_seconds = 120 if case_key == "NS_WAIT_TOO_SHORT" else 360
    contact_complete = case_key != "NS_CONTACT_COVERAGE_INCOMPLETE"
    arrived_at = START
    cancelled_at = START + timedelta(seconds=wait_seconds)
    attempts = [] if case_key == "NS_CONTACT_COVERAGE_INCOMPLETE" else [{"channel": "IN_APP", "at": (START + timedelta(seconds=60)).isoformat()}]
    items = [
        evidence("EV-NS-GPS", case_id, SourceType.PLATFORM_GPS, {"arrival_distance_m": distance_m}),
        evidence(
            "EV-NS-EVENT",
            case_id,
            SourceType.TRIP_EVENT_LOG,
            {
                "arrived_at": arrived_at.isoformat(),
                "cancelled_at": cancelled_at.isoformat(),
                "cancelled_by": "RIDER",
            },
        ),
        evidence(
            "EV-NS-CONTACT",
            case_id,
            SourceType.CONTACT_LOG,
            {"attempts": attempts},
            item_coverage=coverage(contact_complete, "arrival-to-cancellation"),
        ),
        evidence(
            "EV-NS-FARE",
            case_id,
            SourceType.FARE_LEDGER,
            {
                "currency": "SGD",
                "line_items": [{"fee_item": "cancellation_fee", "amount_cents": 400}],
                "total_paid_cents": 400,
            },
        ),
    ]
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=1,
        dispute_type=DisputeType.NO_SHOW,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=START,
        trip_ended_at=END,
        claim_text="The driver did not show up but I was charged a cancellation fee.",
        disputed_fee_item="cancellation_fee",
        disputed_amount_cents=400,
        evidence_refs=tuple(item.evidence_id for item in items),
        created_at=END,
    )
    return snapshot, items


def make_judge(evaluation, *, override_action: Action | None | object = ...):
    action = evaluation.allowed_action if override_action is ... else override_action
    return JudgeRecommendation(
        recommended_case_status=evaluation.business_status,
        recommended_action=action,
        evidence_citations=(),
        policy_citations=evaluation.matched_rule_ids,
        judge_confidence=JudgeConfidence(
            score=72,
            label="UNCALIBRATED_MODEL_SELF_ASSESSMENT",
            rationale="Synthetic consistency-test value",
        ),
        reasoning_summary="Synthetic recommendation",
        rider_explanation="Synthetic rider explanation",
        driver_explanation="Synthetic driver explanation",
    )


class GateBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_policy(POLICY_PATH)
        cls.expected = json.loads(CASES_PATH.read_text(encoding="utf-8"))

    def test_policy_contains_only_versioned_business_rules(self):
        ids = {rule["rule_id"] for rule in self.policy.rules}
        self.assertEqual(13, len(ids))
        self.assertTrue(all(rule_id.startswith(("RD-", "NS-")) for rule_id in ids))

    def test_all_eight_prelabelled_cases(self):
        self.assertEqual(8, len(self.expected))
        for expected in self.expected:
            with self.subTest(case=expected["case_key"]):
                if expected["dispute_type"] == "ROUTE_DEVIATION":
                    snapshot, items = make_route_fixture(expected["case_key"])
                else:
                    snapshot, items = make_no_show_fixture(expected["case_key"])
                result = evaluate_case(snapshot, items, self.policy)
                self.assertEqual(expected["expected_business_status"], result.business_status.value)
                self.assertIn(expected["expected_rule_id"], result.matched_rule_ids)
                if expected["expected_action"] is None:
                    self.assertIsNone(result.allowed_action)
                else:
                    self.assertEqual(expected["expected_action"], result.allowed_action.type.value)
                    self.assertEqual(expected["expected_amount_cents"], result.allowed_action.amount_cents)

    def test_gps_supplement_changes_coverage_deterministically(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        before_gps = aggregate_gps(before, {item.evidence_id: item for item in before_items})
        after_gps = aggregate_gps(after, {item.evidence_id: item for item in after_items})
        self.assertAlmostEqual(70.0, before_gps.coverage_percent)
        self.assertAlmostEqual(100.0, after_gps.coverage_percent)
        self.assertGreater(after_gps.actual_distance_m, before_gps.actual_distance_m)

    def test_overlapping_gps_samples_are_not_double_counted(self):
        snapshot, items = make_route_fixture("RD_UNJUSTIFIED_DEVIATION")
        original = aggregate_gps(snapshot, {item.evidence_id: item for item in items})
        duplicate = evidence(
            "EV-GPS-DUPLICATE",
            snapshot.case_id,
            SourceType.PLATFORM_GPS,
            {"samples": all_samples()[:3]},
            item_coverage=coverage(True, "overlap"),
            role=RecordRole.SUPPLEMENT,
            related=("EV-GPS-FULL",),
        )
        with_duplicate = snapshot.model_copy(update={"evidence_refs": snapshot.evidence_refs + (duplicate.evidence_id,)})
        merged = aggregate_gps(with_duplicate, {item.evidence_id: item for item in items + [duplicate]})
        self.assertFalse(merged.conflict)
        self.assertAlmostEqual(original.coverage_percent, merged.coverage_percent)
        self.assertAlmostEqual(original.actual_distance_m, merged.actual_distance_m)

    def test_conflicting_same_timestamp_gps_requires_review(self):
        snapshot, items = make_route_fixture("RD_UNJUSTIFIED_DEVIATION")
        conflict_sample = dict(all_samples()[0])
        conflict_sample["longitude"] += 0.01
        conflict = evidence(
            "EV-GPS-CONFLICT",
            snapshot.case_id,
            SourceType.PLATFORM_GPS,
            {"samples": [conflict_sample]},
            item_coverage=coverage(False, "conflict"),
            role=RecordRole.SUPPLEMENT,
            related=("EV-GPS-FULL",),
        )
        with_conflict = snapshot.model_copy(update={"evidence_refs": snapshot.evidence_refs + (conflict.evidence_id,)})
        result = evaluate_case(with_conflict, items + [conflict], self.policy)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, result.business_status)
        self.assertIn("GEN-005", result.matched_rule_ids)

    def test_minimal_decision_delta_passes_with_consistent_judges(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        before_result = evaluate_case(before, before_items, self.policy)
        after_result = evaluate_case(after, after_items, self.policy)
        delta = build_decision_delta(
            before,
            after,
            before_result,
            after_result,
            make_judge(before_result),
            make_judge(after_result),
            evidence=after_items,
            policy=self.policy,
        )
        self.assertTrue(delta.comparable)
        self.assertTrue(delta.causal_claim_allowed)
        self.assertEqual("EV-GPS-SUPPLEMENT", delta.changed_evidence_id)
        self.assertEqual("FACT-GPS-COVERAGE-SUFFICIENT", delta.changed_fact_id)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, delta.business_status_before)
        self.assertEqual(BusinessStatus.RESOLVED, delta.business_status_after)
        self.assertEqual(325, delta.refund_delta_cents)

    def test_judge_mismatch_blocks_causal_claim(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        before_result = evaluate_case(before, before_items, self.policy)
        after_result = evaluate_case(after, after_items, self.policy)
        wrong_action = Action(type=ActionType.NO_ACTION, fee_item=None, amount_cents=0, currency="SGD")
        wrong_judge = make_judge(after_result, override_action=wrong_action)
        with self.assertRaises(OutputIntegrityError):
            validate_judge_recommendation(after_result, wrong_judge)
        delta = build_decision_delta(
            before,
            after,
            before_result,
            after_result,
            make_judge(before_result),
            wrong_judge,
            evidence=after_items,
            policy=self.policy,
        )
        self.assertFalse(delta.causal_claim_allowed)
        self.assertFalse(delta.judge_consistent_after)

    def test_delta_rejects_nonexistent_added_evidence(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        before_result = evaluate_case(before, before_items, self.policy)
        after_result = evaluate_case(after, after_items, self.policy)
        phantom_after = after.model_copy(
            update={
                "evidence_refs": tuple(
                    "EV-NONEXISTENT" if item == "EV-GPS-SUPPLEMENT" else item
                    for item in after.evidence_refs
                )
            }
        )
        delta = build_decision_delta(
            before,
            phantom_after,
            before_result,
            after_result,
            make_judge(before_result),
            make_judge(after_result),
            evidence=after_items,
            policy=self.policy,
        )
        self.assertFalse(delta.comparable)
        self.assertFalse(delta.causal_claim_allowed)

    def test_mutated_policy_outcome_is_rejected(self):
        raw = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
        target = next(rule for rule in raw["rules"] if rule["rule_id"] == "RD-004")
        target["allowed_outcome"] = {"action": "NO_ACTION"}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "mutated-policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_policy(path)

    def test_no_show_requires_authoritative_operational_sources(self):
        for source_type in (
            SourceType.PLATFORM_GPS,
            SourceType.TRIP_EVENT_LOG,
            SourceType.CONTACT_LOG,
        ):
            with self.subTest(source_type=source_type):
                snapshot, items = make_no_show_fixture("NS_VALID_CHARGE")
                replaced = []
                for item in items:
                    if item.source_type == source_type:
                        item = item.model_copy(update={"trust_tier": TrustTier.SUPPORTING, "checksum": ""})
                        item = item.model_copy(update={"checksum": compute_evidence_checksum(item)})
                    replaced.append(item)
                result = evaluate_case(snapshot, replaced, self.policy)
                self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, result.business_status)
                self.assertEqual(("NS-001",), result.matched_rule_ids)

    def test_tampered_evidence_checksum_is_rejected_as_integrity_failure(self):
        snapshot, items = make_route_fixture("RD_UNJUSTIFIED_DEVIATION")
        tampered = []
        for item in items:
            if item.evidence_id == "EV-FARE":
                changed_payload = dict(item.payload)
                changed_payload["line_items"] = [
                    {"fee_item": "distance_surcharge", "amount_cents": 999}
                ]
                item = item.model_copy(update={"payload": changed_payload})
            tampered.append(item)
        with self.assertRaises(EvidenceIntegrityError):
            evaluate_case(snapshot, tampered, self.policy)

    def test_no_show_contact_attempt_must_fall_inside_waiting_interval(self):
        snapshot, items = make_no_show_fixture("NS_VALID_CHARGE")
        replaced = []
        for item in items:
            if item.source_type == SourceType.CONTACT_LOG:
                item = item.model_copy(
                    update={
                        "payload": {
                            "attempts": [
                                {
                                    "channel": "IN_APP",
                                    "at": (START + timedelta(minutes=9)).isoformat(),
                                }
                            ]
                        },
                        "checksum": "",
                    }
                )
                item = item.model_copy(update={"checksum": compute_evidence_checksum(item)})
            replaced.append(item)
        result = evaluate_case(snapshot, replaced, self.policy)
        self.assertEqual(BusinessStatus.RESOLVED, result.business_status)
        self.assertEqual(("NS-005",), result.matched_rule_ids)
        self.assertEqual(400, result.allowed_action.amount_cents)

    def test_no_show_complete_contact_log_must_cover_full_waiting_interval(self):
        snapshot, items = make_no_show_fixture("NS_VALID_CHARGE")
        replaced = []
        for item in items:
            if item.source_type == SourceType.CONTACT_LOG:
                short_coverage = Coverage(
                    start_at=START,
                    end_at=START + timedelta(minutes=5),
                    is_complete=True,
                    scope="arrival-to-cancellation",
                )
                item = item.model_copy(update={"coverage": short_coverage, "checksum": ""})
                item = item.model_copy(update={"checksum": compute_evidence_checksum(item)})
            replaced.append(item)
        result = evaluate_case(snapshot, replaced, self.policy)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, result.business_status)
        self.assertEqual(("NS-007",), result.matched_rule_ids)

    def test_delta_rejects_evaluation_from_different_evidence_input(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        before_result = evaluate_case(before, before_items, self.policy)
        after_result = evaluate_case(after, after_items, self.policy)

        original = next(item for item in after_items if item.evidence_id == "EV-GPS-SUPPLEMENT")
        replacement = evidence(
            "EV-GPS-SUPPLEMENT-REISSUED",
            after.case_id,
            SourceType.PLATFORM_GPS,
            original.payload,
            item_coverage=original.coverage,
            role=RecordRole.SUPPLEMENT,
            related=original.related_evidence_ids,
        )
        changed_after = after.model_copy(
            update={
                "evidence_refs": tuple(
                    replacement.evidence_id if item == original.evidence_id else item
                    for item in after.evidence_refs
                )
            }
        )
        changed_evidence = [
            replacement if item.evidence_id == original.evidence_id else item
            for item in after_items
        ]
        delta = build_decision_delta(
            before,
            changed_after,
            before_result,
            after_result,
            make_judge(before_result),
            make_judge(after_result),
            evidence=changed_evidence,
            policy=self.policy,
        )
        self.assertFalse(delta.comparable)
        self.assertFalse(delta.causal_claim_allowed)
        self.assertIn(
            "after evaluation is not bound to the compared snapshot, evidence, and policy",
            delta.not_comparable_reasons,
        )

    def test_conflicting_ledgers_require_human_review(self):
        snapshot, items = make_route_fixture("RD_UNJUSTIFIED_DEVIATION")
        conflicting = evidence(
            "EV-FARE-CONFLICT",
            snapshot.case_id,
            SourceType.FARE_LEDGER,
            {
                "currency": "SGD",
                "line_items": [{"fee_item": "distance_surcharge", "amount_cents": 999}],
                "total_paid_cents": 999,
            },
        )
        snapshot = snapshot.model_copy(update={"evidence_refs": snapshot.evidence_refs + (conflicting.evidence_id,)})
        result = evaluate_case(snapshot, items + [conflicting], self.policy)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, result.business_status)
        self.assertIn("GEN-005", result.matched_rule_ids)

    def test_v2_reuses_v1_ledger_through_snapshot_membership(self):
        before, before_items = make_route_fixture("RD_INCOMPLETE_GPS")
        after, after_items = make_route_fixture("RD_INCOMPLETE_GPS", version=2, supplement=True)
        self.assertIn("EV-FARE", before.evidence_refs)
        self.assertIn("EV-FARE", after.evidence_refs)
        ledgers = [item for item in after_items if item.evidence_id == "EV-FARE"]
        self.assertEqual(1, len(ledgers))
        self.assertFalse(hasattr(ledgers[0], "case_version"))
        result = evaluate_case(after, after_items, self.policy)
        self.assertEqual(BusinessStatus.RESOLVED, result.business_status)

    def test_no_action_contract_is_unambiguous(self):
        with self.assertRaises(ValidationError):
            Action(type=ActionType.NO_ACTION, fee_item="cancellation_fee", amount_cents=0, currency="SGD")
        with self.assertRaises(ValidationError):
            Action(type=ActionType.NO_ACTION, fee_item=None, amount_cents=1, currency="SGD")


if __name__ == "__main__":
    unittest.main()
