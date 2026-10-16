from __future__ import annotations

import json
import unittest

from rideresolve.models import JudgeConfidence, JudgeRecommendation
from rideresolve.policy import OutputIntegrityError
from rideresolve.tool_service import (
    DeterministicEvaluationRequest,
    JudgeValidationRequest,
    ToolScope,
    ToolService,
    TripEvidenceRequest,
)


class DeterministicWorkflowGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = ToolService.load_default()
        cls.scope = ToolScope(
            run_id="RUN-OFFICIAL-DISP-001",
            actor_role="JUDGE",
            case_id="DISP-001",
            case_version=1,
            policy_version="RYDE_POLICY_V2_1",
        )

    @staticmethod
    def recommendation(*, correct: bool) -> JudgeRecommendation:
        if correct:
            action = {
                "type": "REFUND_DISPUTED_FEE_PARTIAL",
                "fee_item": "excess_distance_fare",
                "amount_cents": 344,
                "currency": "SGD",
            }
            status = "RESOLVED"
            policy_citations = ("RD-104",)
        else:
            action = None
            status = "PENDING_HUMAN_REVIEW"
            policy_citations = ("RD-106",)
        return JudgeRecommendation(
            recommended_case_status=status,
            recommended_action=action,
            evidence_citations=(
                "OFFICIAL-DISP-001-GPS",
                "OFFICIAL-DISP-001-BASELINE",
                "OFFICIAL-DISP-001-FARE",
                "OFFICIAL-DISP-001-CHAT",
                "OFFICIAL-DISP-001-TRAFFIC",
            ),
            policy_citations=policy_citations,
            judge_confidence=JudgeConfidence(
                score=90,
                label="UNCALIBRATED_MODEL_SELF_ASSESSMENT",
                rationale="The deterministic result is authoritative.",
            ),
            reasoning_summary="The explanation follows the locked deterministic result.",
            uncertainties=(),
            rider_explanation="The official evidence supports the validated policy result.",
            driver_explanation="The official evidence supports the validated policy result.",
        )

    def test_official_evaluation_is_authoritative_rd_104(self) -> None:
        result = self.service.get_deterministic_evaluation(
            self.scope,
            DeterministicEvaluationRequest(scope="LOCKED_RUN"),
        )
        evaluation = result["evaluation"]
        self.assertEqual("OFFICIAL_OVER_LEGACY_MOCK", result["data_precedence"])
        self.assertEqual("RESOLVED", evaluation["business_status"])
        self.assertEqual(["RD-104"], evaluation["matched_rule_ids"])
        self.assertEqual(344, evaluation["allowed_action"]["amount_cents"])
        self.assertNotIn(
            "OFFICIAL-DISP-001-PROFILES",
            result["decision_evidence_ids"],
        )

    def test_screenshot_rd_106_result_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            OutputIntegrityError,
            "policy citations conflict|status conflicts",
        ):
            self.service.validate_recommendation(
                self.scope,
                JudgeValidationRequest(
                    run_id=self.scope.run_id,
                    recommendation=self.recommendation(correct=False),
                ),
            )

    def test_matching_recommendation_passes_and_returns_short_message(self) -> None:
        result = self.service.validate_recommendation(
            self.scope,
            JudgeValidationRequest(
                run_id=self.scope.run_id,
                recommendation=self.recommendation(correct=True),
            ),
        )
        self.assertEqual("PASSED", result["validation_status"])
        self.assertEqual("PYTHON_DETERMINISTIC_GATE", result["validated_by"])
        self.assertLess(len(result["message"]), 240)
        self.assertIn("SGD 3.44", result["message"])

    def test_serialized_recommendation_is_parsed_then_validated(self) -> None:
        recommendation_json = json.dumps(
            self.recommendation(correct=True).model_dump(mode="json")
        )
        result = self.service.validate_recommendation(
            self.scope,
            JudgeValidationRequest(
                run_id=self.scope.run_id,
                recommendation=recommendation_json,
            ),
        )
        self.assertEqual("PASSED", result["validation_status"])

    def test_double_serialized_recommendation_is_unwrapped_then_validated(self) -> None:
        recommendation_json = json.dumps(
            json.dumps(self.recommendation(correct=True).model_dump(mode="json"))
        )
        result = self.service.validate_recommendation(
            self.scope,
            JudgeValidationRequest(
                run_id=self.scope.run_id,
                recommendation=recommendation_json,
            ),
        )
        self.assertEqual("PASSED", result["validation_status"])

    def test_invalid_serialized_recommendation_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "recommendation must be valid JSON"):
            JudgeValidationRequest(
                run_id=self.scope.run_id,
                recommendation="not JSON",
            )

    def test_run_id_mismatch_is_rejected(self) -> None:
        with self.assertRaisesRegex(OutputIntegrityError, "run_id conflicts"):
            self.service.validate_recommendation(
                self.scope,
                JudgeValidationRequest(
                    run_id="RUN-WRONG",
                    recommendation=self.recommendation(correct=True),
                ),
            )

    def test_decision_facts_projection_is_smaller_and_preserves_material_fields(self) -> None:
        evidence_scope = ToolScope(
            run_id=self.scope.run_id,
            actor_role="EVIDENCE_COLLECTION",
            case_id=self.scope.case_id,
            case_version=self.scope.case_version,
            policy_version=self.scope.policy_version,
        )
        evidence_types = [
            "PLATFORM_GPS",
            "ROUTE_BASELINE",
            "FARE_LEDGER",
            "AUTHENTICATED_CHAT",
            "DEMO_TRAFFIC_FEED",
        ]
        compact = self.service.get_trip_evidence(
            evidence_scope,
            TripEvidenceRequest(evidence_types=evidence_types, detail="DECISION_FACTS"),
        )
        summary = self.service.get_trip_evidence(
            evidence_scope,
            TripEvidenceRequest(evidence_types=evidence_types, detail="SUMMARY"),
        )
        by_type = {item["source_type"]: item["payload"] for item in compact["evidence"]}
        self.assertEqual(24800, by_type["PLATFORM_GPS"]["reported_actual_distance_m"])
        self.assertEqual(20500, by_type["ROUTE_BASELINE"]["baseline_distance_m"])
        self.assertTrue(by_type["DEMO_TRAFFIC_FEED"]["reroute_justified"])
        self.assertFalse(by_type["AUTHENTICATED_CHAT"]["route_notification_sent"])
        self.assertIn(
            {"fee_item": "excess_distance_fare", "amount_cents": 344},
            by_type["FARE_LEDGER"]["line_items"],
        )
        compact_size = len(json.dumps(compact, ensure_ascii=False, separators=(",", ":")))
        summary_size = len(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
        self.assertLess(compact_size, summary_size * 0.5)


if __name__ == "__main__":
    unittest.main()
