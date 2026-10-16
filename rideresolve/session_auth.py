from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

from .run_registry import AgentRole, IssuedRun


class ConnectorAuthorizationError(PermissionError):
    pass


class ConnectorCredentialExpiredError(ConnectorAuthorizationError):
    pass


class RunContextError(PermissionError):
    pass


def _b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64url_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.urlsafe_b64decode(value + padding)
    except (ValueError, TypeError) as exc:
        raise RunContextError("invalid run context") from exc
    if _b64url_encode(decoded) != value:
        raise RunContextError("invalid run context")
    return decoded


def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SessionClaims:
    run_id: str
    case_id: str
    case_version: int
    policy_version: str
    expires_at: datetime


class RunContextSigner:
    """Issue and verify opaque, short-lived run context values.

    The signed value carries no connector credential and cannot change the
    server-side run scope. The registry remains authoritative for status,
    request limits, case version, policy version, and expiry.
    """

    def __init__(
        self,
        key: bytes,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if len(key) < 32:
            raise ValueError("run context signing key must contain at least 32 bytes")
        self._key = key
        self._now = now or (lambda: datetime.now(UTC))

    @classmethod
    def from_base64(
        cls,
        encoded_key: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> "RunContextSigner":
        try:
            key = base64.b64decode(encoded_key, validate=True)
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid base64 run context signing key") from exc
        return cls(key, now=now)

    def issue(self, run: IssuedRun) -> str:
        payload = {
            "v": 1,
            "run_id": run.run_id,
            "case_id": run.case_id,
            "case_version": run.case_version,
            "policy_version": run.policy_version,
            "exp": int(run.expires_at.timestamp()),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        encoded_payload = _b64url_encode(serialized)
        signature = hmac.new(self._key, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded_payload}.{_b64url_encode(signature)}"

    def verify(self, value: str) -> SessionClaims:
        if not value or len(value) > 2048 or value.count(".") != 1:
            raise RunContextError("invalid run context")
        encoded_payload, encoded_signature = value.split(".", 1)
        expected = hmac.new(
            self._key,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        supplied = _b64url_decode(encoded_signature)
        if not hmac.compare_digest(expected, supplied):
            raise RunContextError("invalid run context")
        try:
            payload = json.loads(_b64url_decode(encoded_payload))
            if payload.get("v") != 1:
                raise ValueError("unsupported context version")
            expires_at = datetime.fromtimestamp(int(payload["exp"]), tz=UTC)
            claims = SessionClaims(
                run_id=str(payload["run_id"]),
                case_id=str(payload["case_id"]),
                case_version=int(payload["case_version"]),
                policy_version=str(payload["policy_version"]),
                expires_at=expires_at,
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise RunContextError("invalid run context") from exc
        if self._now() >= claims.expires_at:
            raise RunContextError("run context expired")
        return claims


class ConnectorCredentialSet:
    """Hashed, expiry-bounded credentials for ADP connector definitions."""

    def __init__(
        self,
        *,
        intake_token_hash: str,
        role_token_hashes: dict[AgentRole, str],
        expires_at: datetime,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        if set(role_token_hashes) != set(AgentRole):
            raise ValueError("connector credentials must contain every Agent role")
        hashes = [intake_token_hash, *role_token_hashes.values()]
        if any(len(item) != 64 for item in hashes):
            raise ValueError("connector credential hashes must be SHA-256 hex digests")
        self._intake_token_hash = intake_token_hash.lower()
        self._role_token_hashes = {
            role: digest.lower() for role, digest in role_token_hashes.items()
        }
        self.expires_at = expires_at.astimezone(UTC)
        self._now = now or (lambda: datetime.now(UTC))

    @classmethod
    def from_base64(
        cls,
        encoded: str,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> "ConnectorCredentialSet":
        try:
            raw = json.loads(base64.b64decode(encoded, validate=True))
            if raw.get("schema_version") != 1:
                raise ValueError("unsupported connector credential schema")
            expires_at = datetime.fromisoformat(raw["expires_at"])
            if expires_at.tzinfo is None:
                raise ValueError("connector credential expiry must include a timezone")
            role_hashes = {
                AgentRole(role): str(value["token_hash"])
                for role, value in raw["roles"].items()
            }
            intake_hash = str(raw["intake"]["token_hash"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError("invalid connector credential bundle") from exc
        return cls(
            intake_token_hash=intake_hash,
            role_token_hashes=role_hashes,
            expires_at=expires_at,
            now=now,
        )

    @classmethod
    def from_plaintext(
        cls,
        *,
        intake_token: str,
        role_tokens: dict[AgentRole, str],
        expires_at: datetime,
        now: Callable[[], datetime] | None = None,
    ) -> "ConnectorCredentialSet":
        return cls(
            intake_token_hash=_token_digest(intake_token),
            role_token_hashes={role: _token_digest(token) for role, token in role_tokens.items()},
            expires_at=expires_at,
            now=now,
        )

    def _ensure_active(self) -> None:
        if self._now() >= self.expires_at:
            raise ConnectorCredentialExpiredError("connector credential expired")

    def authorize_intake(self, token: str) -> None:
        self._ensure_active()
        if not token or len(token) > 256:
            raise ConnectorAuthorizationError("invalid connector credential")
        if not secrets.compare_digest(_token_digest(token), self._intake_token_hash):
            raise ConnectorAuthorizationError("invalid connector credential")

    def authorize_role(self, token: str) -> AgentRole:
        self._ensure_active()
        if not token or len(token) > 256:
            raise ConnectorAuthorizationError("invalid connector credential")
        digest = _token_digest(token)
        matched: AgentRole | None = None
        for role, expected in self._role_token_hashes.items():
            if secrets.compare_digest(digest, expected):
                matched = role
        if matched is None:
            raise ConnectorAuthorizationError("invalid connector credential")
        return matched
