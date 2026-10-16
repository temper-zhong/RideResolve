from __future__ import annotations

import unittest

from rideresolve.case_store import CaseStore
from rideresolve.demo_service import advocate_panels, evaluate_demo_case
from rideresolve.models import BusinessStatus
from rideresolve.stretch_goals import (
    build_escalation_packet,
    run_evidence_collection_agent,
)


class EvidenceCollectionAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = CaseStore.load_default()

    def test_incomplete_route_package_is_held_for_supplementation(self):
        report = run_evidence_collection_agent(self.store, "CASE-RD-001", 1)

        self.assertEqual("Evidence Collection Agent", report.agent_name)
        self.assertFalse(report.ready_for_advocates)
        self.assertTrue(any("GPS coverage is 70.0%" in gap for gap in report.gaps))
        self.assertIn("PLATFORM_GPS", report.required_source_types)
        self.assertIn("EV-RD-001-GPS-A", report.collected_evidence_ids)
        self.assertIn("RD-001", report.policy_rule_ids)

    def test_supplemented_route_package_is_ready(self):
        report = run_evidence_collection_agent(self.store, "CASE-RD-001", 2)

        self.assertTrue(report.ready_for_advocates)
        self.assertEqual((), report.gaps)
        self.assertIn("EV-RD-GPS-SUPPLEMENT", report.collected_evidence_ids)
        self.assertEqual(
            {"get_case_snapshot", "get_trip_evidence", "get_policy_rules"},
            {step.operation for step in report.steps},
        )

        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        rider, driver = advocate_panels(case, report.collected_evidence_ids)
        cited = set(rider["citations"]) | set(driver["citations"])
        self.assertTrue(cited)
        self.assertTrue(cited <= set(report.collected_evidence_ids))

    def test_no_show_package_uses_its_required_source_plan(self):
        report = run_evidence_collection_agent(self.store, "CASE-NS-TOOL-001", 1)

        self.assertTrue(report.ready_for_advocates)
        self.assertEqual(
            {"PLATFORM_GPS", "TRIP_EVENT_LOG", "CONTACT_LOG", "FARE_LEDGER"},
            set(report.required_source_types),
        )
        self.assertIn("NS-002", report.policy_rule_ids)


class EscalationProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = CaseStore.load_default()

    def test_pending_case_generates_complete_handoff_packet(self):
        case = evaluate_demo_case(self.store, "CASE-RD-001", 1)
        packet = build_escalation_packet(case)

        self.assertTrue(packet.triggered)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, packet.effective_status)
        self.assertEqual("HUMAN_DISPUTE_REVIEW", packet.queue)
        self.assertIn("EV-RD-001-GPS-A", packet.evidence_ids)
        self.assertEqual(("RD-001",), packet.matched_rule_ids)
        self.assertTrue(any("below the escalation threshold" in reason for reason in packet.trigger_reasons))

    def test_high_confidence_resolved_case_is_not_escalated(self):
        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        packet = build_escalation_packet(case)

        self.assertFalse(packet.triggered)
        self.assertEqual(BusinessStatus.RESOLVED, packet.effective_status)
        self.assertIsNone(packet.queue)

    def test_low_judge_confidence_can_only_escalate_a_resolved_case(self):
        case = evaluate_demo_case(self.store, "CASE-RD-001", 2)
        low_confidence = case.judge.judge_confidence.model_copy(update={"score": 40})
        low_judge = case.judge.model_copy(update={"judge_confidence": low_confidence})
        low_case = case.__class__(
            snapshot=case.snapshot,
            evidence=case.evidence,
            policy=case.policy,
            evaluation=case.evaluation,
            judge=low_judge,
        )

        packet = build_escalation_packet(low_case)

        self.assertTrue(packet.triggered)
        self.assertEqual(BusinessStatus.PENDING_HUMAN_REVIEW, packet.effective_status)
        self.assertEqual("HUMAN_DISPUTE_REVIEW", packet.queue)


if __name__ == "__main__":
    unittest.main()
