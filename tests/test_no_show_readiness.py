from __future__ import annotations

import unittest

from scripts.check_no_show_readiness import build_readiness_report


class NoShowReadinessTests(unittest.TestCase):
    def test_persisted_no_show_fixture_is_ready_without_issuing_credentials(self):
        report = build_readiness_report()

        self.assertTrue(report["ready"])
        self.assertFalse(report["credentials_issued"])
        self.assertEqual("CASE-NS-TOOL-001", report["case_id"])
        self.assertEqual(1, report["case_version"])
        self.assertEqual(
            "RESOLVED",
            report["expected_deterministic_result"]["business_status"],
        )
        self.assertEqual(
            ["NS-002"],
            report["expected_deterministic_result"]["matched_rule_ids"],
        )
        self.assertEqual(
            {
                "type": "NO_ACTION",
                "fee_item": None,
                "amount_cents": 0,
                "currency": "SGD",
            },
            report["expected_deterministic_result"]["allowed_action"],
        )


if __name__ == "__main__":
    unittest.main()
