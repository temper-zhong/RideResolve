from __future__ import annotations

import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from rideresolve.case_store import CaseStore
from rideresolve.run_registry import AgentRole, RunRegistry
from scripts.extend_probe_run_expiry import extend_run_expiry


def _create_fixture(tmp_path: Path) -> tuple[Path, Path, str, datetime]:
    registry_path = tmp_path / "registry.json"
    credential_path = tmp_path / "credential.json"
    now = datetime(2026, 10, 11, tzinfo=UTC)
    registry = RunRegistry(registry_path, CaseStore.load_default(), now=lambda: now)
    issued = registry.create_run("CASE-RD-001", 2, ttl_seconds=3600)
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
            }
        ),
        encoding="utf-8",
    )
    return registry_path, credential_path, issued.run_id, now


def test_extend_run_preserves_tokens_and_updates_deployment_payload(tmp_path: Path) -> None:
    registry_path, credential_path, run_id, now = _create_fixture(tmp_path)
    before = json.loads(credential_path.read_text(encoding="utf-8"))
    target = now + timedelta(days=24)

    encoded = extend_run_expiry(
        registry_path=registry_path,
        credential_path=credential_path,
        run_id=run_id,
        expires_at=target,
    )

    after = json.loads(credential_path.read_text(encoding="utf-8"))
    deployed = json.loads(base64.b64decode(encoded))
    assert after["connector_credentials"] == before["connector_credentials"]
    assert after["expires_at"] == target.isoformat()
    assert deployed["runs"][0]["expires_at"] == target.isoformat()
    assert set(deployed["runs"][0]["credentials"]) == {role.value for role in AgentRole}


def test_extend_run_rejects_hash_mismatch(tmp_path: Path) -> None:
    registry_path, credential_path, run_id, now = _create_fixture(tmp_path)
    credential = json.loads(credential_path.read_text(encoding="utf-8"))
    credential["connector_credentials"][AgentRole.JUDGE.value] = "tampered"
    credential_path.write_text(json.dumps(credential), encoding="utf-8")

    with pytest.raises(ValueError, match="credential hash mismatch"):
        extend_run_expiry(
            registry_path=registry_path,
            credential_path=credential_path,
            run_id=run_id,
            expires_at=now + timedelta(days=24),
        )


def test_extend_run_rejects_more_than_thirty_days(tmp_path: Path) -> None:
    registry_path, credential_path, run_id, now = _create_fixture(tmp_path)

    with pytest.raises(ValueError, match="must not exceed 30 days"):
        extend_run_expiry(
            registry_path=registry_path,
            credential_path=credential_path,
            run_id=run_id,
            expires_at=now + timedelta(days=31),
        )
