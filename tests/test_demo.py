from __future__ import annotations

import unittest

from rideresolve.case_store import CaseStore
from rideresolve.demo_service import (
    chat_semantic_signals,
    evaluate_demo_case,
    historical_context_rows,
    load_delta_demo,
)
from rideresolve.integrity import compute_evidence_checksum
from rideresolve.models import ActionType, BusinessStatus, SourceType, TrustTier
from rideresolve.policy import evaluate_case


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = CaseStore.load_default()

    def test_persisted_delta_pair_produces_expected_policy_chain(self):
        demo = load_delta_demo(self.store)

        self.assertAlmostEqual(70.0, demo.before.evaluation.metrics["gps_coverage_percent"])
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, demo.before.evaluation.business_status)
        self.assertEqual(("RD-001",), demo.before.evaluation.matched_rule_ids)

        self.assertAlmostEqual(100.0, demo.after.evaluation.metrics["gps_coverage_percent"])
        self.assertEqual(BusinessStatus.RESOLVED, demo.after.evaluation.business_status)
        self.assertEqual(("RD-004",), demo.after.evaluation.matched_rule_ids)
        self.assertEqual(ActionType.REFUND_DISPUTED_FEE_FULL, demo.after.evaluation.allowed_action.type)
        self.assertEqual(325, demo.after.evaluation.allowed_action.amount_cents)

        self.assertTrue(demo.delta.comparable)
        self.assertTrue(demo.delta.causal_claim_allowed)
        self.assertEqual("EV-RD-GPS-SUPPLEMENT", demo.delta.changed_evidence_id)
        self.assertEqual("FACT-GPS-COVERAGE-SUFFICIENT", demo.delta.changed_fact_id)
        self.assertEqual(325, demo.delta.refund_delta_cents)

    def test_second_dispute_type_remains_available_to_demo(self):
        case = evaluate_demo_case(self.store, "CASE-NS-TOOL-001", 1)
        self.assertEqual(BusinessStatus.RESOLVED, case.evaluation.business_status)
        self.assertEqual(("NS-002",), case.evaluation.matched_rule_ids)
        self.assertEqual(ActionType.NO_ACTION, case.evaluation.allowed_action.type)

    def test_chat_semantics_are_explicitly_synthetic_and_non_decisional(self):
        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        rows = chat_semantic_signals(case)

        self.assertEqual(2, len(rows))
        self.assertEqual({"CONCERNED", "NEUTRAL"}, {row["Sentiment"] for row in rows})
        self.assertTrue(any(row["Disagreement"] for row in rows))
        self.assertFalse(any(row["Threat"] for row in rows))

        without_labels = []
        for item in case.evidence:
            if item.source_type != SourceType.AUTHENTICATED_CHAT:
                without_labels.append(item)
                continue
            payload = item.model_dump(mode="python")["payload"]
            payload["messages"] = [
                {
                    key: value
                    for key, value in message.items()
                    if key != "synthetic_semantic_labels"
                }
                for message in payload["messages"]
            ]
            updated = item.model_copy(update={"payload": payload, "checksum": ""})
            without_labels.append(
                updated.model_copy(update={"checksum": compute_evidence_checksum(updated)})
            )
        reevaluated = evaluate_case(case.snapshot, without_labels, case.policy)
        self.assertEqual(case.evaluation.business_status, reevaluated.business_status)
        self.assertEqual(case.evaluation.allowed_action, reevaluated.allowed_action)
        self.assertEqual(case.evaluation.matched_rule_ids, reevaluated.matched_rule_ids)

    def test_historical_profiles_are_supporting_and_do_not_change_policy(self):
        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        profiles = [
            item
            for item in case.evidence
            if item.source_type == SourceType.HISTORICAL_BEHAVIOR_PROFILE
        ]
        self.assertEqual(1, len(profiles))
        self.assertEqual(TrustTier.SUPPORTING, profiles[0].trust_tier)
        self.assertEqual(2, len(historical_context_rows(case)))

        without_history = [item for item in case.evidence if item not in profiles]
        snapshot_without_history = case.snapshot.model_copy(
            update={
                "evidence_refs": tuple(
                    evidence_id
                    for evidence_id in case.snapshot.evidence_refs
                    if evidence_id != profiles[0].evidence_id
                )
            }
        )
        reevaluated = evaluate_case(snapshot_without_history, without_history, case.policy)
        self.assertEqual(case.evaluation.business_status, reevaluated.business_status)
        self.assertEqual(case.evaluation.allowed_action, reevaluated.allowed_action)
        self.assertEqual(case.evaluation.matched_rule_ids, reevaluated.matched_rule_ids)


if __name__ == "__main__":
    unittest.main()
