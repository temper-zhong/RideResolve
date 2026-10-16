from __future__ import annotations

import copy
from typing import Any
from urllib.parse import urlparse

from .openapi_schema import build_openapi_schema


ROLE_PATHS: dict[str, tuple[str, ...]] = {
    "evidence": (
        "/tools/get_case_snapshot",
        "/tools/get_trip_evidence",
        "/tools/get_policy_rules",
    ),
    "rider": ("/tools/get_trip_evidence",),
    "driver": ("/tools/get_trip_evidence",),
    "policy": ("/tools/get_policy_rules", "/tools/search_precedents"),
    "gate": (
        "/tools/get_deterministic_evaluation",
        "/tools/validate_recommendation",
    ),
}


ROLE_TITLES = {
    "evidence": "RideResolve Evidence Tools v0.6",
    "rider": "RideResolve Rider Tools v0.6",
    "driver": "RideResolve Driver Tools v0.6",
    "policy": "RideResolve Policy Tools v0.6",
    "gate": "RideResolve Deterministic Gate Tools v0.6 ADP Safe",
}


def _validate_server_url(server_url: str) -> str:
    parsed = urlparse(server_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("server_url must be an explicit HTTPS origin or base path")
    return server_url.rstrip("/")


def build_session_master_schema(server_url: str) -> dict[str, Any]:
    document = copy.deepcopy(build_openapi_schema(server_url))
    document["info"].update(
        {
            "title": "RideResolve Session-Scoped Tools",
            "version": "0.6.0",
            "description": (
                "Role-isolated tools for a server-created workflow session. The static connector "
                "credential authenticates the role; the signed run_context locks the official "
                "case, case version, policy version, expiry, and request budget."
            ),
        }
    )
    for item in document["paths"].values():
        operation = item["post"]
        operation["security"] = [{"ConnectorToken": []}]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        properties = schema.setdefault("properties", {})
        properties["run_context"] = {
            "type": "string",
            "minLength": 40,
            "maxLength": 2048,
            "description": (
                "Opaque signed context returned by resolve_case_context. Pass it unchanged; "
                "never ask a model to create or edit it."
            ),
        }
        required = schema.setdefault("required", [])
        if "run_context" not in required:
            required.insert(0, "run_context")

    # ADP cannot transport a nested object containing JSON null from a Code node to a
    # custom API node: nullable fields are rejected, while opaque objects become {}.
    # Transport the exact parsed Judge recommendation as one JSON string instead. The
    # server parses it and validates the unchanged object with JudgeRecommendation.
    validation_schema = document["paths"]["/tools/validate_recommendation"]["post"][
        "requestBody"
    ]["content"]["application/json"]["schema"]
    validation_schema["properties"]["recommendation"] = {
        "type": "string",
        "minLength": 2,
        "description": (
            "JSON.stringify of parse_judge_json.Output.recommendation. The server parses "
            "and strictly validates this JSON object before evaluating the Gate."
        ),
    }
    document["components"]["securitySchemes"] = {
        "ConnectorToken": {
            "type": "apiKey",
            "in": "header",
            "name": "X-RideResolve-Run-Token",
            "description": (
                "Static, role-specific connector secret. It is expiry-bounded and stored only "
                "in ADP connector authentication settings."
            ),
        }
    }
    return document


def build_session_role_documents(server_url: str) -> dict[str, dict[str, Any]]:
    master = build_session_master_schema(server_url)
    documents: dict[str, dict[str, Any]] = {}
    for role, paths in ROLE_PATHS.items():
        document = copy.deepcopy(master)
        document["info"]["title"] = ROLE_TITLES[role]
        if role == "gate":
            document["info"]["version"] = "0.6.1-adp-json.1"
        document["paths"] = {path: copy.deepcopy(master["paths"][path]) for path in paths}
        documents[role] = document
    return documents


def build_intake_openapi_schema(server_url: str) -> dict[str, Any]:
    server_url = _validate_server_url(server_url)
    result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["resolution_status", "message", "run_created"],
        "properties": {
            "resolution_status": {
                "type": "string",
                "enum": ["MATCHED", "NEEDS_CLARIFICATION", "NOT_FOUND"],
            },
            "message": {"type": "string"},
            "run_created": {"type": "boolean"},
            "run_id": {"type": "string"},
            "run_context": {"type": "string"},
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "policy_version": {"type": "string"},
            "expires_at": {"type": "string", "format": "date-time"},
            "reference_kind": {
                "type": "string",
                "enum": ["CASE_REFERENCE", "TRIP_REFERENCE"],
            },
            "data_precedence": {
                "type": "string",
                "enum": ["OFFICIAL_OVER_LEGACY_MOCK"],
            },
        },
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "RideResolve Official Case Intake v0.6 ADP Safe",
            "version": "0.6.0-adp.1",
            "description": (
                "Resolve an explicit official case or trip reference from a user's description "
                "and create a protected internal workflow session. Vague descriptions are never "
                "matched by similarity and return NEEDS_CLARIFICATION. The ADP-facing request "
                "exposes only SYS.UserQuery to avoid empty optional-field serialization."
            ),
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/tools/resolve_case_context": {
                "post": {
                    "operationId": "resolve_case_context",
                    "summary": "Resolve an official reference and create a workflow session",
                    "description": (
                        "Use first with SYS.UserQuery. Continue to downstream nodes only when "
                        "resolution_status is MATCHED and run_created is true."
                    ),
                    "security": [{"IntakeToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["user_query"],
                                    "properties": {
                                        "user_query": {
                                            "type": "string",
                                            "minLength": 1,
                                            "maxLength": 4000,
                                            "description": "The original external user request from SYS.UserQuery.",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Resolution outcome",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["result", "request_id"],
                                        "properties": {
                                            "result": result_schema,
                                            "request_id": {"type": "string"},
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
        "components": {
            "securitySchemes": {
                "IntakeToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-RideResolve-Intake-Token",
                    "description": "Expiry-bounded secret stored only in ADP connector settings.",
                }
            }
        },
    }
