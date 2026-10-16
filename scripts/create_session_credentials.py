from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
from datetime import UTC, datetime
from pathlib import Path

from rideresolve.run_registry import AgentRole


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create expiry-bounded ADP session connector credentials"
    )
    parser.add_argument("--expires-at", required=True, help="Timezone-aware ISO-8601 timestamp")
    parser.add_argument("--output-directory", required=True, type=Path)
    args = parser.parse_args()

    expires_at = datetime.fromisoformat(args.expires_at)
    if expires_at.tzinfo is None:
        raise SystemExit("--expires-at must include a timezone")
    expires_at = expires_at.astimezone(UTC)
    if expires_at <= datetime.now(UTC):
        raise SystemExit("--expires-at must be in the future")

    intake_token = secrets.token_urlsafe(32)
    role_tokens = {role: secrets.token_urlsafe(32) for role in AgentRole}
    signing_key = secrets.token_bytes(32)
    bundle = {
        "schema_version": 1,
        "expires_at": expires_at.isoformat(),
        "intake": {
            "token_hash": _digest(intake_token),
            "token_id": _digest(intake_token)[:12],
        },
        "roles": {
            role.value: {
                "token_hash": _digest(token),
                "token_id": _digest(token)[:12],
            }
            for role, token in role_tokens.items()
        },
    }
    bundle_bytes = json.dumps(
        bundle,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    output_directory = args.output_directory.resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    secret_values = {
        "expires_at": expires_at.isoformat(),
        "intake": intake_token,
        "roles": {role.value: token for role, token in role_tokens.items()},
    }
    cloudbase_environment = {
        "RIDERESOLVE_CONNECTOR_CREDENTIALS_B64": base64.b64encode(bundle_bytes).decode(
            "ascii"
        ),
        "RIDERESOLVE_CONTEXT_SIGNING_KEY_B64": base64.b64encode(signing_key).decode(
            "ascii"
        ),
    }
    (output_directory / "adp-connector-secret-values.json").write_text(
        json.dumps(secret_values, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_directory / "cloudbase-session-environment.json").write_text(
        json.dumps(cloudbase_environment, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_directory / "hashed-connector-credential-bundle.json").write_text(
        json.dumps(bundle, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"output_directory={output_directory}")
    print(f"expires_at={expires_at.isoformat()}")
    print("secret_values_printed=false")


if __name__ == "__main__":
    main()
