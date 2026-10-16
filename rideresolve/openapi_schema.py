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
        "HISTORICAL_BEHAVIOR_PROFILE",
        "SURGE_PRICING_LOG",
        "NOTIFICATION_LOG",
    ]
    empty_object = {"type": "object", "additionalProperties": False, "properties": {}}

    def successful_response(result_schema: dict[str, Any]) -> dict[str, Any]:
        return {
            "description": "Successful run-scoped tool response",
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

    common_result_properties = {
        "run_id": {"type": "string"},
        "tool_actor_role": {
            "type": "string",
            "enum": [
                "EVIDENCE_COLLECTION",
                "RIDER_ADVOCATE",
                "DRIVER_ADVOCATE",
                "POLICY_PRECEDENT",
                "JUDGE",
            ],
        },
        "dataset_id": {"type": "string"},
        "synthetic": {"type": "boolean"},
    }
    case_schema = {
        "type": "object",
        "additionalProperties": True,
        "required": [
            "case_id",
            "case_version",
            "dispute_type",
            "policy_version",
            "currency",
            "claim_text",
        ],
        "properties": {
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "dispute_type": {"type": "string"},
            "policy_version": {"type": "string"},
            "currency": {"type": "string"},
            "trip_started_at": {"type": "string", "format": "date-time"},
            "trip_ended_at": {"type": "string", "format": "date-time"},
            "claim_text": {"type": "string"},
            "disputed_fee_item": {"type": "string"},
            "disputed_amount_cents": {"type": "integer"},
            "created_at": {"type": "string", "format": "date-time"},
        },
    }
    snapshot_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "dataset_id",
            "synthetic",
            "case",
            "evidence_reference_count",
            "available_evidence_types",
        ],
        "properties": {
            **common_result_properties,
            "case": case_schema,
            "evidence_reference_count": {"type": "integer"},
            "available_evidence_types": {
                "type": "array",
                "items": {"type": "string", "enum": source_types},
            },
        },
    }
    coverage_schema = {
        "type": "object",
        "nullable": True,
        "additionalProperties": False,
        "properties": {
            "start_at": {"type": "string", "format": "date-time"},
            "end_at": {"type": "string", "format": "date-time"},
            "is_complete": {"type": "boolean"},
            "scope": {"type": "string"},
        },
    }
    evidence_payload_schema = {
        "type": "object",
        # Evidence payloads are source-specific and the official hackathon datasets add
        # fields that were not present in the original mock. Keep the envelope strict,
        # while allowing versioned evidence payloads to evolve without breaking ADP.
        "additionalProperties": True,
        "properties": {
            "samples": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "timestamp": {"type": "string", "format": "date-time"},
                        "latitude": {"type": "number"},
                        "longitude": {"type": "number"},
                    },
                },
            },
            "sample_count": {"type": "integer"},
            "first_sample_at": {
                "type": "string",
                "format": "date-time",
                "nullable": True,
            },
            "last_sample_at": {
                "type": "string",
                "format": "date-time",
                "nullable": True,
            },
            "arrival_distance_m": {"type": "number"},
            "reported_actual_distance_m": {"type": "number"},
            "baseline_distance_m": {"type": "number"},
            "currency": {"type": "string"},
            "line_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "fee_item": {"type": "string"},
                        "amount_cents": {"type": "integer"},
                    },
                },
            },
            "total_paid_cents": {"type": "integer"},
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "tag": {"type": "string"},
                        "text": {"type": "string"},
                        "at": {"type": "string", "format": "date-time"},
                    },
                },
            },
            "events": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "type": {"type": "string"},
                        "relevant": {"type": "boolean"},
                        "at": {"type": "string", "format": "date-time"},
                    },
                },
            },
            "attempts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "channel": {"type": "string"},
                        "at": {"type": "string", "format": "date-time"},
                    },
                },
            },
            "arrived_at": {"type": "string", "format": "date-time"},
            "cancelled_at": {"type": "string", "format": "date-time"},
            "cancelled_by": {"type": "string"},
            "claims_oral_stop_request": {"type": "boolean"},
            "decision_use": {"type": "string"},
            "profiles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "party": {"type": "string"},
                        "account_age_days": {"type": "integer"},
                        "completed_trips": {"type": "integer"},
                        "prior_disputes_180d": {"type": "integer"},
                        "rating_pattern": {"type": "string"},
                    },
                },
            },
        },
    }
    evidence_item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "evidence_id",
            "source_type",
            "trust_tier",
            "coverage",
            "record_role",
            "payload",
            "checksum_verified",
        ],
        "properties": {
            "evidence_id": {"type": "string"},
            "source_record_id": {"type": "string"},
            "source_type": {"type": "string", "enum": source_types},
            "trust_tier": {"type": "string"},
            "observed_at": {"type": "string", "format": "date-time"},
            "collected_at": {"type": "string", "format": "date-time"},
            "coverage": coverage_schema,
            "record_role": {"type": "string"},
            "related_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "provenance_reason": {"type": "string", "nullable": True},
            "payload": evidence_payload_schema,
            "checksum_verified": {"type": "boolean"},
        },
    }
    evidence_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "dataset_id",
            "synthetic",
            "case_id",
            "case_version",
            "detail",
            "evidence",
        ],
        "properties": {
            **common_result_properties,
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "detail": {
                "type": "string",
                "enum": ["DECISION_FACTS", "SUMMARY", "FULL"],
            },
            "evidence": {"type": "array", "items": evidence_item_schema},
            "gps_aggregate": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "coverage_percent",
                    "actual_distance_m",
                    "unique_sample_count",
                    "conflict",
                    "conflict_reasons",
                ],
                "properties": {
                    "coverage_percent": {"type": "number"},
                    "actual_distance_m": {"type": "number"},
                    "unique_sample_count": {"type": "integer"},
                    "conflict": {"type": "boolean"},
                    "conflict_reasons": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
        },
    }
    policy_parameters_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "minimum_gps_coverage_percent": {"type": "number"},
            "required_source_types": {
                "type": "array",
                "items": {"type": "string"},
            },
            "maximum_allowed_ratio": {"type": "number"},
            "verifiable_exception_sources": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fee_item": {"type": "string"},
            "maximum_pickup_distance_m": {"type": "number"},
            "minimum_wait_seconds": {"type": "integer"},
            "maximum_time_conflict_seconds": {"type": "integer"},
            "maximum_position_conflict_m": {"type": "number"},
            "maximum_deviation_m": {"type": "number"},
            "minimum_wait_from_scheduled_seconds": {"type": "integer"},
            "required_contact_channels": {
                "type": "array",
                "items": {"type": "string"},
            },
            "fee_cents": {"type": "integer"},
        },
    }
    allowed_outcome_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "business_status": {"type": "string"},
            "action": {"type": "string"},
        },
    }
    policy_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "case_id",
            "case_version",
            "dispute_type",
            "policy_id",
            "policy_version",
            "effective_from",
            "timezone",
            "rules",
            "policy_precedents",
        ],
        "properties": {
            "run_id": {"type": "string"},
            "tool_actor_role": common_result_properties["tool_actor_role"],
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "dispute_type": {"type": "string"},
            "policy_id": {"type": "string"},
            "policy_version": {"type": "string"},
            "effective_from": {"type": "string", "format": "date-time"},
            "effective_to": {
                "type": "string",
                "format": "date-time",
                "nullable": True,
            },
            "timezone": {"type": "string"},
            "rules": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": True,
                    "required": ["rule_id", "dispute_type", "priority", "evaluator"],
                    "properties": {
                        "rule_id": {"type": "string"},
                        "dispute_type": {"type": "string"},
                        "priority": {"type": "integer"},
                        "evaluator": {"type": "string"},
                        "parameters": policy_parameters_schema,
                        "allowed_outcome": allowed_outcome_schema,
                    },
                },
            },
            "policy_precedents": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
    }
    action_schema = {
        "type": "object",
        "nullable": True,
        "additionalProperties": False,
        "required": ["type", "fee_item", "amount_cents", "currency"],
        "properties": {
            "type": {"type": "string"},
            "fee_item": {"type": "string", "nullable": True},
            "amount_cents": {"type": "integer"},
            "currency": {"type": "string"},
        },
    }
    precedent_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "dataset_id",
            "synthetic",
            "knowledge_base_id",
            "authority",
            "may_override_policy",
            "query_context",
            "matches",
            "advisory",
        ],
        "properties": {
            **common_result_properties,
            "knowledge_base_id": {"type": "string"},
            "authority": {"type": "string", "enum": ["ADVISORY_ONLY"]},
            "may_override_policy": {"type": "boolean", "enum": [False]},
            "query_context": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "case_id",
                    "case_version",
                    "dispute_type",
                    "policy_version",
                    "matched_rule_ids",
                ],
                "properties": {
                    "case_id": {"type": "string"},
                    "case_version": {"type": "integer"},
                    "dispute_type": {"type": "string"},
                    "policy_version": {"type": "string"},
                    "matched_rule_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
            },
            "matches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "precedent_id",
                        "similarity_score",
                        "source_case_id",
                        "source_rule_ids",
                        "corrected_status",
                        "corrected_action",
                        "correction_reason",
                    ],
                    "properties": {
                        "precedent_id": {"type": "string"},
                        "similarity_score": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                        },
                        "source_case_id": {"type": "string"},
                        "source_rule_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "corrected_status": {"type": "string"},
                        "corrected_action": action_schema,
                        "correction_reason": {"type": "string"},
                    },
                },
            },
            "advisory": {"type": "string"},
        },
    }
    judge_confidence_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["score", "label", "rationale"],
        "properties": {
            "score": {"type": "integer", "minimum": 0, "maximum": 100},
            "label": {
                "type": "string",
                "enum": ["UNCALIBRATED_MODEL_SELF_ASSESSMENT"],
            },
            "rationale": {"type": "string"},
        },
    }
    recommendation_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "recommended_case_status",
            "recommended_action",
            "evidence_citations",
            "policy_citations",
            "judge_confidence",
            "reasoning_summary",
            "uncertainties",
            "rider_explanation",
            "driver_explanation",
        ],
        "properties": {
            "recommended_case_status": {
                "type": "string",
                "enum": ["RESOLVED", "PENDING_HUMAN_REVIEW"],
            },
            "recommended_action": action_schema,
            "evidence_citations": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "policy_citations": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string"},
            },
            "judge_confidence": judge_confidence_schema,
            "reasoning_summary": {"type": "string"},
            "uncertainties": {
                "type": "array",
                "items": {"type": "string"},
            },
            "rider_explanation": {"type": "string"},
            "driver_explanation": {"type": "string"},
        },
    }
    recommendation_transport_schema = {
        "oneOf": [
            recommendation_schema,
            {
                "type": "string",
                "minLength": 2,
                "description": (
                    "Serialized JudgeRecommendation accepted for ADP transport. "
                    "The service unwraps one additional JSON-string transport layer "
                    "before applying the same strict validation."
                ),
            },
        ]
    }
    policy_evaluation_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "business_status",
            "matched_rule_ids",
            "allowed_action",
            "evaluated_by",
            "facts",
            "metrics",
            "review_reasons",
            "input_fingerprint",
        ],
        "properties": {
            "business_status": {"type": "string"},
            "matched_rule_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "allowed_action": action_schema,
            "evaluated_by": {
                "type": "string",
                "enum": ["DETERMINISTIC_POLICY_CODE"],
            },
            "facts": {
                "type": "object",
                "additionalProperties": {"type": "string"},
            },
            "metrics": {
                "type": "object",
                "additionalProperties": {"type": "number"},
            },
            "review_reasons": {
                "type": "array",
                "items": {"type": "string"},
            },
            "input_fingerprint": {"type": "string"},
        },
    }
    deterministic_evaluation_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "dataset_id",
            "synthetic",
            "case_id",
            "case_version",
            "dispute_type",
            "policy_version",
            "data_precedence",
            "decision_evidence_ids",
            "evaluation",
            "message",
        ],
        "properties": {
            **common_result_properties,
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "dispute_type": {"type": "string"},
            "policy_version": {"type": "string"},
            "data_precedence": {
                "type": "string",
                "enum": ["OFFICIAL_OVER_LEGACY_MOCK"],
            },
            "decision_evidence_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "evaluation": policy_evaluation_schema,
            "message": {"type": "string"},
        },
    }
    validation_result_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "run_id",
            "tool_actor_role",
            "dataset_id",
            "synthetic",
            "case_id",
            "case_version",
            "policy_version",
            "validation_status",
            "validated_by",
            "message",
            "recommendation",
            "authoritative_evaluation",
        ],
        "properties": {
            **common_result_properties,
            "case_id": {"type": "string"},
            "case_version": {"type": "integer"},
            "policy_version": {"type": "string"},
            "validation_status": {"type": "string", "enum": ["PASSED"]},
            "validated_by": {
                "type": "string",
                "enum": ["PYTHON_DETERMINISTIC_GATE"],
            },
            "message": {"type": "string"},
            "recommendation": recommendation_schema,
            "authoritative_evaluation": policy_evaluation_schema,
        },
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "RideResolve Multi-Agent Read-Only Tools",
            "version": "0.6.2",
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
                    "responses": {"200": successful_response(snapshot_result_schema)},
                }
            },
            "/tools/get_trip_evidence": {
                "post": {
                    "operationId": "get_trip_evidence",
                    "summary": "Get selected evidence authorized for this probe run",
                    "description": (
                        "Returns only evidence in the server-side run manifest. Prefer "
                        "DECISION_FACTS; request SUMMARY or FULL only for human audit."
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
                                            "maxItems": 12,
                                            "items": {"type": "string", "enum": source_types},
                                        },
                                        "detail": {
                                            "type": "string",
                                            "enum": ["DECISION_FACTS", "SUMMARY", "FULL"],
                                            "default": "DECISION_FACTS",
                                        },
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": successful_response(evidence_result_schema)},
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
                                    "required": ["scope"],
                                    "properties": {
                                        "scope": {
                                            "type": "string",
                                            "enum": ["APPLICABLE_DISPUTE"],
                                            "description": (
                                                "Return the current run's policy rules for its "
                                                "locked dispute type."
                                            ),
                                        },
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
                    "responses": {"200": successful_response(policy_result_schema)},
                }
            },
            "/tools/search_precedents": {
                "post": {
                    "operationId": "search_precedents",
                    "summary": "Search approved advisory precedents for this run",
                    "description": (
                        "Policy context and matched rules are derived server-side from the locked "
                        "case snapshot. Results are advisory-only and cannot override policy."
                    ),
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "limit": {
                                            "type": "integer",
                                            "minimum": 1,
                                            "maximum": 3,
                                            "default": 3,
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": successful_response(precedent_result_schema)},
                }
            },
            "/tools/get_deterministic_evaluation": {
                "post": {
                    "operationId": "get_deterministic_evaluation",
                    "summary": "Evaluate the locked run with deterministic policy code",
                    "description": (
                        "Workflow-owned gate operation. Official case data and its pinned policy "
                        "version take precedence over legacy mock assumptions."
                    ),
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["scope"],
                                    "properties": {
                                        "scope": {
                                            "type": "string",
                                            "enum": ["LOCKED_RUN"],
                                        }
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": successful_response(deterministic_evaluation_result_schema)
                    },
                }
            },
            "/tools/validate_recommendation": {
                "post": {
                    "operationId": "validate_recommendation",
                    "summary": "Reject a Judge recommendation that conflicts with the locked run",
                    "description": (
                        "Workflow-owned final gate. It verifies run identity, citations, status, "
                        "action, amount, currency, and the deterministic policy result."
                    ),
                    "security": [{"RunToken": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["run_id", "recommendation"],
                                    "properties": {
                                        "run_id": {"type": "string"},
                            "recommendation": recommendation_transport_schema,
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": successful_response(validation_result_schema),
                        "409": {"description": "Recommendation conflicts with deterministic policy"},
                    },
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
