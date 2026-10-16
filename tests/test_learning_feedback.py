from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from rideresolve.case_store import CaseStore
from rideresolve.demo_service import evaluate_demo_case
from rideresolve.learning_feedback import (
    FeedbackIntegrityError,
    PrecedentKnowledgeBase,
    capture_reviewer_correction,
    feedback_loop_steps,
    run_policy_precedent_agent,
)
from rideresolve.models import Action, ActionType, BusinessStatus, DisputeType


def feedback_fields(feedback_id: str = "FB-TEST-001") -> dict[str, object]:
    return {
        "feedback_id": feedback_id,
        "source_case_id": "CASE-RD-HIST-TEST",
        "source_case_version": 1,
        "dispute_type": DisputeType.ROUTE_DEVIATION,
        "policy_version": "DEMO_POLICY_V1",
        "reviewed_at": datetime(2026, 10, 8, tzinfo=timezone.utc),
        "reviewer_role": "HUMAN_REVIEWER",
        "original_status": BusinessStatus.RESOLVED,
        "original_action": Action(
            type=ActionType.REFUND_DISPUTED_FEE_FULL,
            fee_item="distance_surcharge",
            amount_cents=325,
            currency="SGD",
        ),
        "corrected_status": BusinessStatus.PENDING_HUMAN_REVIEW,
        "corrected_action": None,
        "source_rule_ids": ("RD-004",),
        "evidence_citations": ("EV-HIST-A", "EV-HIST-B"),
        "correction_reason": (
            "A late authoritative ledger conflicted with the original amount basis and required review."
        ),
        "publication_status": "APPROVED_FOR_PRECEDENT",
        "learning_scope": "ADVISORY_PRECEDENT_ONLY",
    }


class LearningFeedbackLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = CaseStore.load_default()

    def test_default_knowledge_base_loads_verified_synthetic_override(self):
        knowledge_base = PrecedentKnowledgeBase.load_default()

        self.assertTrue(knowledge_base.synthetic)
        self.assertEqual(4, len(knowledge_base.records))
        self.assertEqual("FB-RD-004-001", knowledge_base.records[0].feedback_id)
        self.assertTrue(all(record.synthetic for record in knowledge_base.records))
        self.assertEqual("ADVISORY_PRECEDENT_ONLY", knowledge_base.records[0].learning_scope)

    def test_feedback_requires_a_genuine_outcome_change(self):
        fields = feedback_fields()
        fields["corrected_status"] = fields["original_status"]
        fields["corrected_action"] = fields["original_action"]

        with self.assertRaises(ValidationError):
            capture_reviewer_correction(**fields)

    def test_tampered_feedback_cannot_be_published(self):
        record = capture_reviewer_correction(**feedback_fields())
        tampered = record.model_copy(update={"correction_reason": "Tampered after approval."})

        with self.assertRaises(FeedbackIntegrityError):
            PrecedentKnowledgeBase.empty().publish(tampered)

    def test_approved_feedback_is_published_and_retrieved_for_judge_context(self):
        record = capture_reviewer_correction(**feedback_fields())
        knowledge_base = PrecedentKnowledgeBase.empty().publish(record)
        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        original_evaluation = case.evaluation

        report = run_policy_precedent_agent(case, knowledge_base)

        self.assertEqual(1, len(report.matches))
        self.assertEqual("FB-TEST-001", report.matches[0].feedback_id)
        self.assertEqual("ADVISORY_ONLY", report.judge_context["authority"])
        self.assertFalse(report.judge_context["may_override_policy"])
        self.assertFalse(report.may_change_policy_or_outcome)
        self.assertIs(original_evaluation, case.evaluation)
        self.assertEqual(4, len(feedback_loop_steps(knowledge_base, report)))

    def test_approved_feedback_persists_and_reloads_from_precedent_memory(self):
        record = capture_reviewer_correction(**feedback_fields())
        knowledge_base = PrecedentKnowledgeBase.empty().publish(record)

        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "approved_precedents.json"
            knowledge_base.save(path)
            reloaded = PrecedentKnowledgeBase.load(path)

        self.assertEqual(knowledge_base, reloaded)

    def test_persisted_feedback_cannot_be_removed_by_a_later_save(self):
        record = capture_reviewer_correction(**feedback_fields())
        knowledge_base = PrecedentKnowledgeBase.empty().publish(record)

        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "approved_precedents.json"
            knowledge_base.save(path)
            with self.assertRaises(FeedbackIntegrityError):
                PrecedentKnowledgeBase.empty().save(path)

    def test_irrelevant_precedent_is_not_returned_for_no_show(self):
        case = evaluate_demo_case(self.store, "CASE-NS-TOOL-001", 1)
        report = run_policy_precedent_agent(case)

        self.assertEqual((), report.matches)
        self.assertEqual([], report.judge_context["precedent_ids"])

    def test_policy_conflicting_precedent_remains_advisory(self):
        case = evaluate_demo_case(self.store, "CASE-NS_DRIVER_TOO_FAR", 1)

        report = run_policy_precedent_agent(case)

        self.assertEqual(ActionType.REFUND_DISPUTED_FEE_FULL, case.evaluation.allowed_action.type)
        self.assertEqual(1, len(report.matches))
        self.assertEqual(
            "FB-NS-003-POLICY-CONFLICT-001",
            report.matches[0].feedback_id,
        )
        self.assertEqual(ActionType.NO_ACTION, report.matches[0].corrected_action.type)
        self.assertFalse(report.judge_context["may_override_policy"])
        self.assertFalse(report.may_change_policy_or_outcome)


if __name__ == "__main__":
    unittest.main()
