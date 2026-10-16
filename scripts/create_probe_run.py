from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

from rideresolve.case_store import CaseStore
from rideresolve.run_registry import RunRegistry


ROOT = Path(__file__).resolve().parents[1]


def build_single_run_registry(registry_path: Path, run_id: str) -> bytes:
    registry_payload = json.loads(registry_path.read_text(encoding="utf-8"))
    matching_runs = [
        manifest
        for manifest in registry_payload.get("runs", [])
        if manifest.get("run_id") == run_id
    ]
    if len(matching_runs) != 1:
        raise ValueError(f"expected exactly one manifest for {run_id}")
    deployment_payload = {
        "schema_version": registry_payload.get("schema_version"),
        "runs": matching_runs,
    }
    return json.dumps(
        deployment_payload,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create one short-lived five-role ADP probe run"
    )
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--case-version", required=True, type=int)
    parser.add_argument("--ttl-seconds", default=3600, type=int)
    parser.add_argument("--max-requests-per-role", default=12, type=int)
    parser.add_argument("--registry", type=Path, default=ROOT / "var" / "run_registry.json")
    parser.add_argument("--credentials-dir", type=Path, default=ROOT / "var" / "probe_credentials")
    args = parser.parse_args()

    store = CaseStore.load_default()
    registry = RunRegistry(args.registry, store)
    issued = registry.create_run(
        args.case_id,
        args.case_version,
        ttl_seconds=args.ttl_seconds,
        max_requests_per_role=args.max_requests_per_role,
    )
    args.credentials_dir.mkdir(parents=True, exist_ok=True)
    credential_path = args.credentials_dir / f"{issued.run_id}.json"
    credential_path.write_text(
        json.dumps(
            {
                "run_id": issued.run_id,
                "case_id": issued.case_id,
                "case_version": issued.case_version,
                "policy_version": issued.policy_version,
                "expires_at": issued.expires_at.isoformat(),
                "connector_credentials": {
                    role.value: token for role, token in issued.tokens.items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    deployment_registry_path = args.credentials_dir / f"{issued.run_id}.registry.b64.txt"
    deployment_registry_path.write_text(
        base64.b64encode(
            build_single_run_registry(args.registry, issued.run_id)
        ).decode("ascii")
        + "\n",
        encoding="ascii",
    )
    print(f"Created {issued.run_id}")
    print(f"Credential file: {credential_path}")
    print(f"Hashed deployment registry: {deployment_registry_path}")
    print("Do not paste its contents into prompts, chat, tool descriptions, or screenshots.")


if __name__ == "__main__":
    main()
