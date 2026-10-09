from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.create_probe_run import build_single_run_registry


class CreateProbeRunTests(unittest.TestCase):
    def test_deployment_registry_contains_only_requested_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            registry_path = Path(temporary) / "registry.json"
            registry_path.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "runs": [
                            {"run_id": "RUN-old", "credentials": {}},
                            {"run_id": "RUN-current", "credentials": {}},
                        ],
                    }
                ),
                encoding="utf-8",
            )

            deployment = json.loads(
                build_single_run_registry(registry_path, "RUN-current")
            )

        self.assertEqual(1, deployment["schema_version"])
        self.assertEqual(["RUN-current"], [run["run_id"] for run in deployment["runs"]])


if __name__ == "__main__":
    unittest.main()
