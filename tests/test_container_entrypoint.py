from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import container_entrypoint


class ContainerEntrypointTests(unittest.TestCase):
    def test_startup_refuses_missing_single_instance_acknowledgement(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(SystemExit, "min and max instances are both 1"):
                container_entrypoint.main()

    def test_acknowledgement_does_not_bypass_missing_registry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            missing = Path(temporary) / "missing-registry.json"
            environment = {
                "RIDERESOLVE_SINGLE_INSTANCE_ACK": "MIN_1_MAX_1_CONFIRMED",
                "RIDERESOLVE_RUN_REGISTRY": str(missing),
            }
            with patch.dict(os.environ, environment, clear=True):
                with self.assertRaisesRegex(SystemExit, "No run registry is available"):
                    container_entrypoint.main()


if __name__ == "__main__":
    unittest.main()
