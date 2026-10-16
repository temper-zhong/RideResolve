from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

from rideresolve.run_registry import AgentRole


ROOT = Path(__file__).resolve().parents[1]
MAX_RUN_LIFETIME = timedelta(days=30)


def _parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("expires-at must include a UTC offset")
    return parsed.astimezone(UTC)


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _atomic_json_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def extend_run_expiry(
    *,
    registry_path: Path,
    credential_path: Path,
    run_id: str,
    expires_at: datetime,
) -> bytes:
    """Extend one active run after verifying all five raw tokens against their hashes."""
    expires_at = expires_at.astimezone(UTC)
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    credential = json.loads(credential_path.read_text(encoding="utf-8"))

    matching = [item for item in registry.get("runs", []) if item.get("run_id") == run_id]
    if len(matching) != 1:
        raise ValueError(f"expected exactly one manifest for {run_id}")
    manifest = matching[0]
    if manifest.get("status") != "ACTIVE":
        raise ValueError("only an ACTIVE run can be extended")
    if credential.get("run_id") != run_id:
        raise ValueError("credential file belongs to a different run")

    created_at = _parse_aware_datetime(manifest["created_at"])
    current_expiry = _parse_aware_datetime(manifest["expires_at"])
    if expires_at <= current_expiry:
        raise ValueError("new expiry must be later than the current expiry")
    if expires_at <= datetime.now(UTC):
        raise ValueError("new expiry must be in the future")
    if expires_at - created_at > MAX_RUN_LIFETIME:
        raise ValueError("extended run lifetime must not exceed 30 days")

    expected_roles = {role.value for role in AgentRole}
    manifest_credentials = manifest.get("credentials", {})
    raw_credentials = credential.get("connector_credentials", {})
    if set(manifest_credentials) != expected_roles or set(raw_credentials) != expected_roles:
        raise ValueError("registry and credential file must contain exactly the five roles")
    for role in expected_roles:
        raw_token = raw_credentials[role]
        if not isinstance(raw_token, str) or not raw_token:
            raise ValueError(f"missing raw credential for {role}")
        if _token_digest(raw_token) != manifest_credentials[role].get("token_hash"):
            raise ValueError(f"credential hash mismatch for {role}")

    expiry_text = expires_at.isoformat()
    manifest["expires_at"] = expiry_text
    credential["expires_at"] = expiry_text

    _atomic_json_write(registry_path, registry)
    _atomic_json_write(credential_path, credential)

    deployment_payload = {"schema_version": registry.get("schema_version"), "runs": [manifest]}
    return base64.b64encode(
        json.dumps(
            deployment_payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Extend one existing five-role probe run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expires-at", required=True, help="ISO 8601 timestamp with UTC offset")
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--deployment-registry", type=Path, required=True)
    args = parser.parse_args()

    encoded = extend_run_expiry(
        registry_path=args.registry,
        credential_path=args.credential_file,
        run_id=args.run_id,
        expires_at=_parse_aware_datetime(args.expires_at),
    )
    args.deployment_registry.parent.mkdir(parents=True, exist_ok=True)
    args.deployment_registry.write_bytes(encoded + b"\n")
    print(f"Extended {args.run_id} to {_parse_aware_datetime(args.expires_at).isoformat()}")
    print(f"Hashed deployment registry: {args.deployment_registry}")
    print("Raw role credentials were verified but were not printed or changed.")


if __name__ == "__main__":
    main()
