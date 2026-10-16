from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


def metrics(app: AppTest) -> dict[str, str]:
    return {item.label: item.value for item in app.metric}


class StreamlitDemoTests(unittest.TestCase):
    def setUp(self):
        self.app = AppTest.from_file(ROOT / "app.py", default_timeout=20).run()
        self.assertEqual([], list(self.app.exception))

    def test_default_delta_v1_is_pending_and_clearly_synthetic(self):
        values = metrics(self.app)
        self.assertEqual("CASE-RD-001", values["Case"])
        self.assertEqual("v1", values["Version"])
        self.assertEqual("Pending human review", values["Final status"])
        self.assertEqual("SGD 0.00", values["Refund"])
        self.assertGreaterEqual(len(self.app.table), 7)
        self.assertGreaterEqual(len(self.app.warning), 2)
        self.assertEqual("NEEDS SUPPLEMENT", values["Package status"])
        self.assertEqual("TRIGGERED", values["Escalation"])
        self.assertEqual("4", values["Approved corrections"])
        self.assertEqual("0", values["Matched precedents"])

    def test_delta_v2_renders_simulated_refund(self):
        v2_option = self.app.radio[0].options[1]
        self.app.radio[0].set_value(v2_option).run()
        self.assertEqual([], list(self.app.exception))
        values = metrics(self.app)
        self.assertEqual("v2", values["Version"])
        self.assertEqual("Simulated resolution complete", values["Final status"])
        self.assertEqual("REFUND_DISPUTED_FEE_FULL", values["Action"])
        self.assertEqual("SGD 3.25", values["Refund"])
        self.assertEqual("100/100", values["Evidence completeness"])
        self.assertEqual("READY", values["Package status"])
        self.assertEqual("NOT REQUIRED", values["Escalation"])
        self.assertEqual("2", values["Matched precedents"])

    def test_no_show_scenario_renders_second_dispute_type(self):
        no_show_option = self.app.sidebar.selectbox[0].options[1]
        self.app.sidebar.selectbox[0].set_value(no_show_option).run()
        self.assertEqual([], list(self.app.exception))
        values = metrics(self.app)
        self.assertEqual("CASE-NS-TOOL-001", values["Case"])
        self.assertEqual("No Show", values["Dispute"])
        self.assertEqual("NO_ACTION", values["Action"])
        self.assertEqual("Simulated resolution complete", values["Final status"])
        self.assertEqual("0", values["Matched precedents"])


if __name__ == "__main__":
    unittest.main()
