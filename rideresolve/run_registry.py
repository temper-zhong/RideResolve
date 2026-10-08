from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Callable

from .case_store import CaseStore


class AgentRole(StrEnum):
    RIDER_ADVOCATE = "RIDER_ADVOCATE"
    DRIVER_ADVOCATE = "DRIVER_ADVOCATE"
    JUDGE = "JUDGE"


class RunAuthorizationError(PermissionError):
    pass


class RunTokenExpiredError(RunAuthorizationError):
    pass


class RunRequestLimitError(RunAuthorizationError):
    pass


@dataclass(frozen=True)
class RunAuthorization:
    run_id: str
    role: AgentRole
    case_id: str
    case_version: int
    policy_version: str
    expires_at: datetime
    token_id: str
    request_number: int


@dataclass(frozen=True)
class IssuedRun:
    run_id: str
    case_id: str
    case_version: int
    policy_version: str
    expires_at: datetime
    tokens: dict[AgentRole, str]


@dataclass(frozen=True)
class RunManifestScope:
    run_id: str
    case_id: str
    case_version: int
    policy_version: str
    created_at: datetime
    expires_at: datetime
    status: str


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RunRegistry:
    """Persistent probe-run manifests containing token hashes, never raw tokens."""

    def __init__(
        self,
        path: Path,
        store: CaseStore,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.path = path
        self.store = store
        self._now = now or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()

    def _load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "runs": []}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != 1 or not isinstance(raw.get("runs"), list):
            raise ValueError("unsupported run registry format")
        return raw

    def _save(self, raw: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)

    def create_run(
        self,
        case_id: str,
        case_version: int,
        *,
        ttl_seconds: int = 3600,
        max_requests_per_role: int = 12,
    ) -> IssuedRun:
        if ttl_seconds < 60 or ttl_seconds > 4 * 3600:
            raise ValueError("ttl_seconds must be between 60 and 14400")
        if max_requests_per_role < 1 or max_requests_per_role > 30:
            raise ValueError("max_requests_per_role must be between 1 and 30")
        snapshot = self.store.get_snapshot(case_id, case_version)
        created_at = self._now()
        expires_at = created_at + timedelta(seconds=ttl_seconds)
        run_id = f"RUN-{uuid.uuid4().hex}"
        tokens = {role: secrets.token_urlsafe(32) for role in AgentRole}
        manifest = {
            "run_id": run_id,
            "case_id": snapshot.case_id,
            "case_version": snapshot.case_version,
            "policy_version": snapshot.policy_version,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "status": "ACTIVE",
            "max_requests_per_role": max_requests_per_role,
            "credentials": {
                role.value: {
                    "token_hash": _token_digest(token),
                    "token_id": _token_digest(token)[:12],
                    "request_count": 0,
                }
                for role, token in tokens.items()
            },
        }
        with self._lock:
            raw = self._load()
            raw["runs"].append(manifest)
            self._save(raw)
        return IssuedRun(
            run_id=run_id,
            case_id=snapshot.case_id,
            case_version=snapshot.case_version,
            policy_version=snapshot.policy_version,
            expires_at=expires_at,
            tokens=tokens,
        )

    def authorize_and_consume(self, token: str) -> RunAuthorization:
        if not token or len(token) > 256:
            raise RunAuthorizationError("invalid run credential")
        digest = _token_digest(token)
        with self._lock:
            raw = self._load()
            for manifest in raw["runs"]:
                for role_value, credential in manifest["credentials"].items():
                    if not secrets.compare_digest(digest, credential["token_hash"]):
                        continue
                    expires_at = datetime.fromisoformat(manifest["expires_at"])
                    if manifest.get("status") != "ACTIVE":
                        raise RunAuthorizationError("run is not active")
                    if self._now() >= expires_at:
                        raise RunTokenExpiredError("run credential expired")
                    if credential["request_count"] >= manifest["max_requests_per_role"]:
                        raise RunRequestLimitError("run request limit exceeded")
                    credential["request_count"] += 1
                    request_number = credential["request_count"]
                    self._save(raw)
                    return RunAuthorization(
                        run_id=manifest["run_id"],
                        role=AgentRole(role_value),
                        case_id=manifest["case_id"],
                        case_version=manifest["case_version"],
                        policy_version=manifest["policy_version"],
                        expires_at=expires_at,
                        token_id=credential["token_id"],
                        request_number=request_number,
                    )
        raise RunAuthorizationError("invalid run credential")

    def revoke_run(self, run_id: str) -> None:
        with self._lock:
            raw = self._load()
            for manifest in raw["runs"]:
                if manifest["run_id"] == run_id:
                    manifest["status"] = "REVOKED"
                    self._save(raw)
                    return
        raise LookupError(f"run not found: {run_id}")

    def get_manifest_scope(self, run_id: str) -> RunManifestScope:
        with self._lock:
            raw = self._load()
            for manifest in raw["runs"]:
                if manifest["run_id"] == run_id:
                    return RunManifestScope(
                        run_id=manifest["run_id"],
                        case_id=manifest["case_id"],
                        case_version=manifest["case_version"],
                        policy_version=manifest["policy_version"],
                        created_at=datetime.fromisoformat(manifest["created_at"]),
                        expires_at=datetime.fromisoformat(manifest["expires_at"]),
                        status=manifest["status"],
                    )
        raise LookupError(f"run not found: {run_id}")
