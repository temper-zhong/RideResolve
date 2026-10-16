from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .case_store import CaseNotFoundError, PolicyNotFoundError
from .intake import IntakeRequest, IntakeService, OfficialCaseResolver
from .openapi_schema import build_openapi_schema
from .policy import OutputIntegrityError
from .run_registry import (
    AgentRole,
    RunAuthorization,
    RunAuthorizationError,
    RunRegistry,
    RunRequestLimitError,
    RunTokenExpiredError,
)
from .session_auth import (
    ConnectorAuthorizationError,
    ConnectorCredentialExpiredError,
    ConnectorCredentialSet,
    RunContextError,
    RunContextSigner,
)
from .tool_audit import JsonlAuditLogger
from .tool_service import (
    CaseSnapshotRequest,
    DeterministicEvaluationRequest,
    JudgeValidationRequest,
    PolicyRulesRequest,
    PrecedentSearchRequest,
    ToolScope,
    ToolService,
    TripEvidenceRequest,
)


MAX_BODY_BYTES = 64 * 1024

_INTAKE_PATH = "/tools/resolve_case_context"
_CASE_PATH = "/tools/get_case_snapshot"
_EVIDENCE_PATH = "/tools/get_trip_evidence"
_POLICY_PATH = "/tools/get_policy_rules"
_PRECEDENT_PATH = "/tools/search_precedents"
_EVALUATION_PATH = "/tools/get_deterministic_evaluation"
_VALIDATION_PATH = "/tools/validate_recommendation"
_KNOWN_TOOL_PATHS = frozenset(
    {
        _CASE_PATH,
        _EVIDENCE_PATH,
        _POLICY_PATH,
        _PRECEDENT_PATH,
        _EVALUATION_PATH,
        _VALIDATION_PATH,
    }
)
_ROLE_PATH_PERMISSIONS: dict[AgentRole, frozenset[str]] = {
    AgentRole.EVIDENCE_COLLECTION: frozenset(
        {_CASE_PATH, _EVIDENCE_PATH, _POLICY_PATH}
    ),
    AgentRole.RIDER_ADVOCATE: frozenset({_EVIDENCE_PATH}),
    AgentRole.DRIVER_ADVOCATE: frozenset({_EVIDENCE_PATH}),
    AgentRole.POLICY_PRECEDENT: frozenset({_POLICY_PATH, _PRECEDENT_PATH}),
    # These credentials belong to workflow-owned deterministic nodes. They are
    # never attached to the Judge model itself.
    AgentRole.JUDGE: frozenset({_EVALUATION_PATH, _VALIDATION_PATH}),
}


def _presented_token_id(token: str) -> str | None:
    if not token:
        return None
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


def _returned_ids(result: dict[str, Any]) -> dict[str, list[str]]:
    evidence_ids = [
        item["evidence_id"]
        for item in result.get("evidence", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    ]
    rule_ids = [
        item["rule_id"]
        for item in result.get("rules", [])
        if isinstance(item, dict) and isinstance(item.get("rule_id"), str)
    ]
    precedent_ids = [
        item["precedent_id"]
        for item in result.get("matches", [])
        if isinstance(item, dict) and isinstance(item.get("precedent_id"), str)
    ]
    evidence_ids.extend(
        item
        for item in result.get("decision_evidence_ids", [])
        if isinstance(item, str) and item not in evidence_ids
    )
    evaluation = result.get("evaluation") or result.get("authoritative_evaluation") or {}
    rule_ids.extend(
        item
        for item in evaluation.get("matched_rule_ids", [])
        if isinstance(item, str) and item not in rule_ids
    )
    return {
        "evidence_ids": evidence_ids,
        "rule_ids": rule_ids,
        "precedent_ids": precedent_ids,
    }


def _safe_validation_summary(exc: ValidationError, body_size: int) -> dict[str, Any]:
    errors = exc.errors(include_url=False, include_input=False)
    return {
        "body_size_bytes": body_size,
        "validation_error_count": len(errors),
        "validation_error_types": sorted({str(item.get("type", "unknown")) for item in errors}),
    }


def create_http_server(
    host: str,
    port: int,
    *,
    registry: RunRegistry,
    audit_logger: JsonlAuditLogger,
    service: ToolService | None = None,
    openapi_server_url: str | None = None,
    connector_credentials: ConnectorCredentialSet | None = None,
    run_context_signer: RunContextSigner | None = None,
    intake_service: IntakeService | None = None,
) -> ThreadingHTTPServer:
    if (connector_credentials is None) != (run_context_signer is None):
        raise ValueError("connector credentials and run context signer must be configured together")
    if intake_service is not None and connector_credentials is None:
        raise ValueError("intake service requires connector credentials")
    tool_service = service or ToolService.load_default()
    server_instance_id = f"INSTANCE-{uuid.uuid4().hex}"
    openapi_document = (
        build_openapi_schema(openapi_server_url) if openapi_server_url is not None else None
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "RideResolveTools/0.6"

        def _request_id(self) -> str:
            # Never trust or retain a caller-supplied correlation value. The response
            # carries this server-generated ID and ADP must record that returned value.
            return f"rr-{uuid.uuid4().hex}"

        def _send_json(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _complete(
            self,
            *,
            status: int,
            payload: dict[str, Any],
            request_id: str,
            started_at: datetime,
            started_clock: float,
            endpoint: str,
            authorization: RunAuthorization | None,
            presented_token_id: str | None,
            parameters: dict[str, Any] | None = None,
            returned_ids: dict[str, list[str]] | None = None,
            error_code: str | None = None,
        ) -> None:
            ended_at = datetime.now(UTC)
            audit_logger.append(
                {
                    "schema_version": 1,
                    "request_id": request_id,
                    "server_instance_id": server_instance_id,
                    "run_id": authorization.run_id if authorization else None,
                    "token_id": authorization.token_id if authorization else presented_token_id,
                    "actor_role": authorization.role.value if authorization else None,
                    "endpoint": endpoint,
                    "case_id": authorization.case_id if authorization else None,
                    "case_version": authorization.case_version if authorization else None,
                    "policy_version": authorization.policy_version if authorization else None,
                    "request_number_for_role": (
                        authorization.request_number if authorization else None
                    ),
                    "parameters": parameters or {},
                    "returned_ids": returned_ids
                    or {"evidence_ids": [], "rule_ids": [], "precedent_ids": []},
                    "started_at": started_at.isoformat(),
                    "ended_at": ended_at.isoformat(),
                    "duration_ms": round((time.perf_counter() - started_clock) * 1000, 3),
                    "http_status": int(status),
                    "outcome": "SUCCESS" if 200 <= int(status) < 300 else "REJECTED",
                    "error_code": error_code,
                }
            )
            self._send_json(status, payload)

        def _error(
            self,
            status: int,
            code: str,
            message: str,
            *,
            request_id: str,
            started_at: datetime,
            started_clock: float,
            authorization: RunAuthorization | None = None,
            presented_token_id: str | None = None,
            parameters: dict[str, Any] | None = None,
        ) -> None:
            self._complete(
                status=status,
                payload={"error": {"code": code, "message": message}, "request_id": request_id},
                request_id=request_id,
                started_at=started_at,
                started_clock=started_clock,
                endpoint=self.path,
                authorization=authorization,
                presented_token_id=presented_token_id,
                parameters=parameters,
                error_code=code,
            )

        def _read_json_payload(
            self,
            *,
            request_id: str,
            started_at: datetime,
            started_clock: float,
            authorization: RunAuthorization | None,
            presented_token_id: str | None,
        ) -> tuple[dict[str, Any], int] | None:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._error(
                    HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
                    "UNSUPPORTED_MEDIA_TYPE",
                    "Content-Type must be application/json",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    presented_token_id=presented_token_id,
                )
                return None
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                content_length = 0
            if content_length <= 0 or content_length > MAX_BODY_BYTES:
                self._error(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    "INVALID_BODY_SIZE",
                    f"request body must be between 1 and {MAX_BODY_BYTES} bytes",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    presented_token_id=presented_token_id,
                )
                return None
            try:
                payload = json.loads(self.rfile.read(content_length))
            except (json.JSONDecodeError, UnicodeDecodeError):
                self._error(
                    HTTPStatus.BAD_REQUEST,
                    "INVALID_JSON",
                    "request body is not valid JSON",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    presented_token_id=presented_token_id,
                )
                return None
            if not isinstance(payload, dict):
                self._error(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    "VALIDATION_ERROR",
                    "request validation failed",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    presented_token_id=presented_token_id,
                    parameters={"body_size_bytes": content_length},
                )
                return None
            return payload, content_length

        def _handle_intake(
            self,
            *,
            request_id: str,
            started_at: datetime,
            started_clock: float,
        ) -> None:
            token = self.headers.get("X-RideResolve-Intake-Token", "")
            token_id = _presented_token_id(token)
            if intake_service is None or connector_credentials is None:
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "NOT_FOUND",
                    "route not found",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            try:
                connector_credentials.authorize_intake(token)
            except ConnectorCredentialExpiredError:
                self._error(
                    HTTPStatus.UNAUTHORIZED,
                    "CONNECTOR_CREDENTIAL_EXPIRED",
                    "connector credential expired",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            except ConnectorAuthorizationError:
                self._error(
                    HTTPStatus.UNAUTHORIZED,
                    "UNAUTHORIZED",
                    "invalid connector credential",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            parsed = self._read_json_payload(
                request_id=request_id,
                started_at=started_at,
                started_clock=started_clock,
                authorization=None,
                presented_token_id=token_id,
            )
            if parsed is None:
                return
            payload, content_length = parsed
            try:
                validated = IntakeRequest.model_validate(payload)
                result = intake_service.resolve_case_context(validated)
            except ValidationError as exc:
                summary = _safe_validation_summary(exc, content_length)
                self._complete(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    payload={
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "request validation failed",
                            "details": summary,
                        },
                        "request_id": request_id,
                    },
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    endpoint=self.path,
                    authorization=None,
                    presented_token_id=token_id,
                    parameters=summary,
                    error_code="VALIDATION_ERROR",
                )
                return
            except Exception:
                self._error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_ERROR",
                    "intake execution failed",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            self._complete(
                status=HTTPStatus.OK,
                payload={"result": result, "request_id": request_id},
                request_id=request_id,
                started_at=started_at,
                started_clock=started_clock,
                endpoint=self.path,
                authorization=None,
                presented_token_id=token_id,
                parameters={
                    "resolution_status": result["resolution_status"],
                    "run_created": result["run_created"],
                    "reference_kind": result.get("reference_kind"),
                },
            )

        def do_GET(self) -> None:  # noqa: N802
            request_id = self._request_id()
            if self.path == "/health":
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "service": "rideresolve-tools",
                        "dataset_id": tool_service.store.dataset_id,
                        "synthetic": tool_service.store.synthetic,
                        "session_mode_enabled": connector_credentials is not None,
                        "request_id": request_id,
                        "server_instance_id": server_instance_id,
                    },
                )
                return
            if self.path == "/openapi.json" and openapi_document is not None:
                self._send_json(HTTPStatus.OK, openapi_document)
                return
            self._send_json(
                HTTPStatus.NOT_FOUND,
                {"error": {"code": "NOT_FOUND", "message": "route not found"}, "request_id": request_id},
            )

        def do_POST(self) -> None:  # noqa: N802
            request_id = self._request_id()
            started_at = datetime.now(UTC)
            started_clock = time.perf_counter()
            if self.path == _INTAKE_PATH:
                self._handle_intake(
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                )
                return
            token = self.headers.get("X-RideResolve-Run-Token", "")
            token_id = _presented_token_id(token)
            payload: dict[str, Any] | None = None
            content_length = 0
            try:
                authorization = registry.authorize_and_consume(token)
            except RunRequestLimitError:
                self._error(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    "RUN_REQUEST_LIMIT_EXCEEDED",
                    "run request limit exceeded",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            except RunTokenExpiredError:
                self._error(
                    HTTPStatus.UNAUTHORIZED,
                    "RUN_TOKEN_EXPIRED",
                    "run credential expired",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    presented_token_id=token_id,
                )
                return
            except RunAuthorizationError:
                if connector_credentials is None or run_context_signer is None:
                    self._error(
                        HTTPStatus.UNAUTHORIZED,
                        "UNAUTHORIZED",
                        "invalid run credential",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        presented_token_id=token_id,
                    )
                    return
                try:
                    role = connector_credentials.authorize_role(token)
                except ConnectorCredentialExpiredError:
                    self._error(
                        HTTPStatus.UNAUTHORIZED,
                        "CONNECTOR_CREDENTIAL_EXPIRED",
                        "connector credential expired",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        presented_token_id=token_id,
                    )
                    return
                except ConnectorAuthorizationError:
                    self._error(
                        HTTPStatus.UNAUTHORIZED,
                        "UNAUTHORIZED",
                        "invalid run credential",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        presented_token_id=token_id,
                    )
                    return
                parsed = self._read_json_payload(
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=None,
                    presented_token_id=token_id,
                )
                if parsed is None:
                    return
                payload, content_length = parsed
                context_value = payload.pop("run_context", None)
                try:
                    claims = run_context_signer.verify(context_value)
                    authorization = registry.authorize_context_and_consume(
                        claims.run_id,
                        role,
                        token_id=token_id or "connector",
                    )
                    if (
                        claims.case_id != authorization.case_id
                        or claims.case_version != authorization.case_version
                        or claims.policy_version != authorization.policy_version
                        # The signed ``exp`` claim is a NumericDate with whole-second
                        # precision. The registry intentionally keeps the original
                        # microseconds, so compare both values at the precision that
                        # was authenticated instead of rejecting a valid context.
                        or int(claims.expires_at.timestamp())
                        != int(authorization.expires_at.timestamp())
                    ):
                        raise RunContextError("run context scope mismatch")
                except RunRequestLimitError:
                    self._error(
                        HTTPStatus.TOO_MANY_REQUESTS,
                        "RUN_REQUEST_LIMIT_EXCEEDED",
                        "run request limit exceeded",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        presented_token_id=token_id,
                    )
                    return
                except (RunAuthorizationError, RunContextError, TypeError):
                    self._error(
                        HTTPStatus.UNAUTHORIZED,
                        "INVALID_RUN_CONTEXT",
                        "invalid or expired run context",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        presented_token_id=token_id,
                    )
                    return

            if (
                self.path in _KNOWN_TOOL_PATHS
                and self.path not in _ROLE_PATH_PERMISSIONS[authorization.role]
            ):
                self._error(
                    HTTPStatus.FORBIDDEN,
                    "ROLE_NOT_ALLOWED",
                    "this Agent role is not allowed to call the requested operation",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                )
                return

            if payload is None:
                parsed = self._read_json_payload(
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    presented_token_id=None,
                )
                if parsed is None:
                    return
                payload, content_length = parsed

            scope = ToolScope(
                run_id=authorization.run_id,
                actor_role=authorization.role.value,
                case_id=authorization.case_id,
                case_version=authorization.case_version,
                policy_version=authorization.policy_version,
            )
            audit_parameters: dict[str, Any] = {}
            try:
                if self.path == _CASE_PATH:
                    validated_request = CaseSnapshotRequest.model_validate(payload)
                    result = tool_service.get_case_snapshot(scope, validated_request)
                elif self.path == _EVIDENCE_PATH:
                    validated_request = TripEvidenceRequest.model_validate(payload)
                    audit_parameters = {
                        "evidence_type_count": len(validated_request.evidence_types or ()),
                        "detail": validated_request.detail,
                    }
                    result = tool_service.get_trip_evidence(scope, validated_request)
                elif self.path == _POLICY_PATH:
                    validated_request = PolicyRulesRequest.model_validate(payload)
                    audit_parameters = {
                        "scope": validated_request.scope,
                        "rule_id_count": len(validated_request.rule_ids or ()),
                    }
                    result = tool_service.get_policy_rules(scope, validated_request)
                elif self.path == _PRECEDENT_PATH:
                    validated_request = PrecedentSearchRequest.model_validate(payload)
                    audit_parameters = {"limit": validated_request.limit}
                    result = tool_service.search_precedents(scope, validated_request)
                elif self.path == _EVALUATION_PATH:
                    validated_request = DeterministicEvaluationRequest.model_validate(payload)
                    audit_parameters = {"scope": validated_request.scope}
                    result = tool_service.get_deterministic_evaluation(scope, validated_request)
                elif self.path == _VALIDATION_PATH:
                    validated_request = JudgeValidationRequest.model_validate(payload)
                    audit_parameters = {
                        "evidence_citation_count": len(
                            validated_request.recommendation.evidence_citations
                        ),
                        "policy_citation_count": len(
                            validated_request.recommendation.policy_citations
                        ),
                    }
                    result = tool_service.validate_recommendation(scope, validated_request)
                else:
                    self._error(
                        HTTPStatus.NOT_FOUND,
                        "NOT_FOUND",
                        "route not found",
                        request_id=request_id,
                        started_at=started_at,
                        started_clock=started_clock,
                        authorization=authorization,
                        parameters={},
                    )
                    return
            except ValidationError as exc:
                validation_summary = _safe_validation_summary(exc, content_length)
                self._complete(
                    status=HTTPStatus.UNPROCESSABLE_ENTITY,
                    payload={
                        "error": {
                            "code": "VALIDATION_ERROR",
                            "message": "request validation failed",
                            "details": validation_summary,
                        },
                        "request_id": request_id,
                    },
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    endpoint=self.path,
                    authorization=authorization,
                    presented_token_id=None,
                    parameters=validation_summary,
                    error_code="VALIDATION_ERROR",
                )
                return
            except (CaseNotFoundError, PolicyNotFoundError) as exc:
                self._error(
                    HTTPStatus.NOT_FOUND,
                    "RESOURCE_NOT_FOUND",
                    str(exc),
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                )
                return
            except OutputIntegrityError as exc:
                self._error(
                    HTTPStatus.CONFLICT,
                    "RECOMMENDATION_CONFLICT",
                    str(exc),
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                    parameters=audit_parameters,
                )
                return
            except Exception:
                self._error(
                    HTTPStatus.INTERNAL_SERVER_ERROR,
                    "INTERNAL_ERROR",
                    "tool execution failed",
                    request_id=request_id,
                    started_at=started_at,
                    started_clock=started_clock,
                    authorization=authorization,
                )
                return

            self._complete(
                status=HTTPStatus.OK,
                payload={"result": result, "request_id": request_id},
                request_id=request_id,
                started_at=started_at,
                started_clock=started_clock,
                endpoint=self.path,
                authorization=authorization,
                presented_token_id=None,
                parameters=audit_parameters,
                returned_ids=_returned_ids(result),
            )

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    server.rideresolve_instance_id = server_instance_id  # type: ignore[attr-defined]
    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the RideResolve read-only probe tool API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=int(os.environ.get("PORT", "8000")), type=int)
    parser.add_argument("--registry", default=os.environ.get("RIDERESOLVE_RUN_REGISTRY", "var/run_registry.json"))
    parser.add_argument("--audit-log", default=os.environ.get("RIDERESOLVE_AUDIT_LOG", "var/tool_audit.jsonl"))
    parser.add_argument("--public-url", default=os.environ.get("RIDERESOLVE_PUBLIC_URL"))
    args = parser.parse_args()
    service = ToolService.load_default()
    registry = RunRegistry(Path(args.registry), service.store)
    audit_logger = JsonlAuditLogger(Path(args.audit_log), emit_stdout=True)
    encoded_connector_credentials = os.environ.get(
        "RIDERESOLVE_CONNECTOR_CREDENTIALS_B64", ""
    ).strip()
    encoded_signing_key = os.environ.get(
        "RIDERESOLVE_CONTEXT_SIGNING_KEY_B64", ""
    ).strip()
    if bool(encoded_connector_credentials) != bool(encoded_signing_key):
        raise SystemExit(
            "Session mode requires both RIDERESOLVE_CONNECTOR_CREDENTIALS_B64 "
            "and RIDERESOLVE_CONTEXT_SIGNING_KEY_B64."
        )
    connector_credentials = None
    run_context_signer = None
    intake_service = None
    if encoded_connector_credentials:
        connector_credentials = ConnectorCredentialSet.from_base64(
            encoded_connector_credentials
        )
        run_context_signer = RunContextSigner.from_base64(encoded_signing_key)
        intake_service = IntakeService(
            OfficialCaseResolver(service.store),
            registry,
            run_context_signer,
            max_requests_per_role=300,
        )
    server = create_http_server(
        args.host,
        args.port,
        registry=registry,
        audit_logger=audit_logger,
        service=service,
        openapi_server_url=args.public_url,
        connector_credentials=connector_credentials,
        run_context_signer=run_context_signer,
        intake_service=intake_service,
    )
    print(
        "RIDEREsolve_INSTANCE_START "
        + json.dumps(
            {
                "server_instance_id": getattr(server, "rideresolve_instance_id"),
                "started_at": datetime.now(UTC).isoformat(),
                "host": args.host,
                "port": args.port,
            },
            separators=(",", ":"),
        ),
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
