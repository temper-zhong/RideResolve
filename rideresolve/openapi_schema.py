from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def build_openapi_schema(server_url: str) -> dict[str, Any]:
    parsed = urlparse(server_url)
    if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError("server_url must be an explicit HTTPS origin or base path")
    source_types = [
        "PLATFORM_GPS",
        "FARE_LEDGER",
        "ROUTE_BASELINE",
        "TRIP_EVENT_LOG",
        "CONTACT_LOG",
        "AUTHENTICATED_CHAT",
        "DEMO_TRAFFIC_FEED",
        "PARTY_STATEMENT",
    ]
    empty_object = {"type": "object", "additionalProperties": False, "properties": {}}
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "RideResolve Gate A Probe Tools",
            "version": "0.2.0",
            "description": (
                "Read-only tools for synthetic RideResolve cases. The secure connector credential "
                "is a short-lived, role-specific run token and must never appear in model input."
            ),
        },
        "servers": [{"url": server_url.rstrip("/")}],
        "paths": {
            "/tools/get_case_snapshot": {
                "post": {
                    "operationId": "get_case_snapshot",
                    "summary": "Get the case summary authorized for this probe run",
                    "description": (
                        "Use first. Evidence IDs are intentionally omitted so evidence citations "
                        "must come from get_trip_evidence."
                    ),
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": empty_object}},
                    },
                    "responses": {"200": {"description": "Run-scoped case summary"}},
                }
            },
            "/tools/get_trip_evidence": {
                "post": {
                    "operationId": "get_trip_evidence",
                    "summary": "Get selected evidence authorized for this probe run",
                    "description": (
                        "Returns only evidence in the server-side run manifest. Prefer SUMMARY "
                        "unless raw GPS samples are necessary."
                    ),
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["evidence_types"],
                                    "properties": {
                                        "evidence_types": {
                                            "type": "array",
                                            "minItems": 1,
                                            "maxItems": 8,
                                            "items": {"type": "string", "enum": source_types},
                                        },
                                        "detail": {
                                            "type": "string",
                                            "enum": ["SUMMARY", "FULL"],
                                            "default": "SUMMARY",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Run-scoped evidence records"}},
                }
            },
            "/tools/get_policy_rules": {
                "post": {
                    "operationId": "get_policy_rules",
                    "summary": "Get policy rules authorized for this probe run",
                    "description": "The policy version and dispute type come from the server-side run manifest.",
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "rule_ids": {
                                            "type": "array",
                                            "minItems": 1,
                                            "maxItems": 20,
                                            "items": {"type": "string"},
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Run-scoped policy rules"}},
                }
            },
        },
        "components": {
            "securitySchemes": {
                "RunToken": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-RideResolve-Run-Token",
                    "description": "Short-lived role-specific credential configured only in the connector secret store.",
                }
            }
        },
    }
