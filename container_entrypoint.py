from __future__ import annotations

import base64
import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    if os.environ.get("RIDERESOLVE_SINGLE_INSTANCE_ACK") != "MIN_1_MAX_1_CONFIRMED":
        raise SystemExit(
            "Probe deployment refused: set RIDERESOLVE_SINGLE_INSTANCE_ACK="
            "MIN_1_MAX_1_CONFIRMED only after CloudBase min and max instances are both 1."
        )
    registry_path = Path(os.environ.get("RIDERESOLVE_RUN_REGISTRY", "/tmp/run_registry.json"))
    encoded_registry = os.environ.get("RIDERESOLVE_RUN_REGISTRY_B64", "").strip()
    if encoded_registry:
        registry_path.parent.mkdir(parents=True, exist_ok=True)
        registry_path.write_bytes(base64.b64decode(encoded_registry, validate=True))
    if not registry_path.exists():
        raise SystemExit(
            "No run registry is available. Set RIDERESOLVE_RUN_REGISTRY_B64 to the hashed probe registry."
        )
    environment = dict(os.environ)
    environment["RIDERESOLVE_RUN_REGISTRY"] = str(registry_path)
    environment.setdefault("RIDERESOLVE_AUDIT_LOG", "/tmp/tool_audit.jsonl")
    command = [
        sys.executable,
        "-m",
        "rideresolve.tool_api",
        "--host",
        "0.0.0.0",
        "--port",
        environment.get("PORT", "8080"),
    ]
    raise SystemExit(subprocess.call(command, env=environment))


if __name__ == "__main__":
    main()
