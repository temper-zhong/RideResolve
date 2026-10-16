from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path
from typing import Any

from rideresolve.integrity import compute_evidence_checksum
from rideresolve.models import Evidence


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_SOURCE_DIR = ROOT / "data" / "official_sources"
CASE_OUTPUT = ROOT / "data" / "cases" / "official_cases.json"
POLICY_OUTPUT = ROOT / "data" / "policies" / "RYDE_POLICY_V2_1.json"
MANIFEST_OUTPUT = OFFICIAL_SOURCE_DIR / "source_manifest.json"


def extract_json(path: Path) -> dict[str, Any]:
    match = re.search(
        r"```(?:json)?\s*\n(.*?)\n```",
        path.read_text(encoding="utf-8"),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if match is None:
        raise ValueError(f"No JSON code block found in {path.name}")
    return json.loads(match.group(1))


def cents(value: Any) -> int:
    return int(round(float(value) * 100))


def evidence(**fields: Any) -> dict[str, Any]:
    draft = Evidence.model_validate({**fields, "checksum": ""})
    return draft.model_copy(update={"checksum": compute_evidence_checksum(draft)}).model_dump(
        mode="json"
    )


def coverage(start_at: str, end_at: str, scope: str) -> dict[str, Any]:
    return {
        "start_at": start_at,
        "end_at": end_at,
        "is_complete": True,
        "scope": scope,
    }


def gps_samples(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": item["timestamp"],
            "latitude": item["lat"],
            "longitude": item["lng"],
            **{
                key: value
                for key, value in item.items()
                if key not in {"timestamp", "lat", "lng"}
            },
        }
        for item in raw
    ]


def build_route_case(raw: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_id = raw["dispute_ticket"]["dispute_id"]
    trip = raw["trip_data"]
    filed_at = raw["dispute_ticket"]["filed_at"]
    start_at = trip["start_time"]
    end_at = trip["end_time"]
    refs = [
        "OFFICIAL-DISP-001-GPS",
        "OFFICIAL-DISP-001-BASELINE",
        "OFFICIAL-DISP-001-FARE",
        "OFFICIAL-DISP-001-CHAT",
        "OFFICIAL-DISP-001-TRAFFIC",
        "OFFICIAL-DISP-001-PROFILES",
    ]
    records = [
        evidence(
            evidence_id=refs[0],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":gps",
            source_type="PLATFORM_GPS",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "official complete trip GPS trail"),
            provenance_reason="Official hackathon DISP-001 GPS telemetry; official values override conflicting mock values.",
            payload={
                "samples": gps_samples(raw["gps_telemetry"]),
                "reported_actual_distance_m": trip["actual_distance_km"] * 1000,
                "official_evidence_complete": True,
            },
        ),
        evidence(
            evidence_id=refs[1],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":recommended-route",
            source_type="ROUTE_BASELINE",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "recommended route at booking"),
            provenance_reason="Official hackathon DISP-001 system-recommended route.",
            payload={
                "baseline_distance_m": trip["estimated_distance_km"] * 1000,
                "estimated_duration_min": trip["estimated_duration_min"],
                "optimal_route": raw["optimal_route"],
            },
        ),
        evidence(
            evidence_id=refs[2],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":fare",
            source_type="FARE_LEDGER",
            trust_tier="AUTHORITATIVE",
            observed_at=end_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-001 fare breakdown.",
            payload={
                "currency": "SGD",
                "estimated_total_cents": cents(trip["estimated_fare"]),
                "actual_total_cents": cents(trip["actual_fare"]),
                "line_items": [
                    {"fee_item": "fare_difference", "amount_cents": cents(trip["excess_fare"])},
                    {"fee_item": "excess_distance_fare", "amount_cents": cents(raw["fare_breakdown"]["excess_distance_fare"])},
                    {"fee_item": "excess_tolls", "amount_cents": cents(raw["fare_breakdown"]["excess_tolls"])},
                ],
                "official_fare_breakdown": raw["fare_breakdown"],
            },
        ),
        evidence(
            evidence_id=refs[3],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":chat",
            source_type="AUTHENTICATED_CHAT",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "complete in-app trip chat"),
            provenance_reason="Official hackathon DISP-001 authenticated chat and notification analysis.",
            payload={
                "messages": raw["chat_logs"],
                **raw["chat_log_analysis"],
                "verbal_notification_verified": False,
            },
        ),
        evidence(
            evidence_id=refs[4],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":traffic",
            source_type="DEMO_TRAFFIC_FEED",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "official traffic incidents relevant to trip"),
            provenance_reason="Official hackathon DISP-001 traffic conditions and supplied traffic analysis.",
            payload={
                "events": raw["traffic_conditions"],
                **raw["traffic_analysis"],
            },
        ),
        evidence(
            evidence_id=refs[5],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":profiles",
            source_type="HISTORICAL_BEHAVIOR_PROFILE",
            trust_tier="SUPPORTING",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-001 rider and driver profile context; not primary liability evidence.",
            payload={"rider": raw["rider_profile"], "driver": raw["driver_profile"]},
        ),
    ]
    snapshot = {
        "case_id": case_id,
        "case_version": 1,
        "dispute_type": "ROUTE_DEVIATION",
        "policy_version": "RYDE_POLICY_V2_1",
        "currency": "SGD",
        "trip_started_at": start_at,
        "trip_ended_at": end_at,
        "claim_text": raw["dispute_ticket"]["description"],
        "disputed_fee_item": "fare_difference",
        "disputed_amount_cents": cents(trip["excess_fare"]),
        "evidence_refs": refs,
        "created_at": filed_at,
    }
    expected = {
        "case_id": case_id,
        "case_version": 1,
        "business_status": "RESOLVED",
        "matched_rule_ids": ["RD-104"],
        "action": {
            "type": "REFUND_DISPUTED_FEE_PARTIAL",
            "fee_item": "excess_distance_fare",
            "amount_cents": 344,
            "currency": "SGD",
        },
        "official_expected_ruling": raw["case_metadata"]["expected_ruling"],
    }
    return snapshot, records, expected


def build_no_show_case(raw: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_id = raw["dispute_ticket"]["dispute_id"]
    trip = raw["trip_data"]
    filed_at = raw["dispute_ticket"]["filed_at"]
    start_at = trip["driver_arrival_time"]
    end_at = trip["cancellation_time"]
    refs = [
        "OFFICIAL-DISP-002-GPS",
        "OFFICIAL-DISP-002-EVENTS",
        "OFFICIAL-DISP-002-CONTACT",
        "OFFICIAL-DISP-002-FARE",
        "OFFICIAL-DISP-002-PROFILES",
    ]
    attempts = [
        {
            "at": item["timestamp"],
            "channel": "PHONE" if item["type"] == "call" else "IN_APP_CHAT",
            "sender": item["sender"],
            "content": item["content"],
        }
        for item in raw["chat_logs"]
        if item["type"] in {"message", "call"} and item["sender"] == "driver"
    ]
    records = [
        evidence(
            evidence_id=refs[0],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":gps",
            source_type="PLATFORM_GPS",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "driver presence during official no-show interval"),
            provenance_reason="Official hackathon DISP-002 GPS telemetry.",
            payload={
                "samples": gps_samples(raw["gps_telemetry"]),
                "arrival_distance_m": 0,
                "pickup_location": trip["pickup_location"],
            },
        ),
        evidence(
            evidence_id=refs[1],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":events",
            source_type="TRIP_EVENT_LOG",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "complete official arrival-to-cancellation events"),
            provenance_reason="Official hackathon DISP-002 app event log.",
            payload={
                "scheduled_at": trip["scheduled_time"],
                "arrived_at": trip["driver_arrival_time"],
                "cancelled_at": trip["cancellation_time"],
                "cancelled_by": "DRIVER",
                "events": raw["app_events"],
            },
        ),
        evidence(
            evidence_id=refs[2],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":contacts",
            source_type="CONTACT_LOG",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "complete official driver contact interval"),
            provenance_reason="Official hackathon DISP-002 in-app messages and call record.",
            payload={"attempts": attempts, "raw_chat_logs": raw["chat_logs"]},
        ),
        evidence(
            evidence_id=refs[3],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":fare",
            source_type="FARE_LEDGER",
            trust_tier="AUTHORITATIVE",
            observed_at=end_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-002 fixed no-show cancellation fee.",
            payload={
                "currency": "SGD",
                "line_items": [{"fee_item": "cancellation_fee", "amount_cents": cents(trip["cancellation_fee"])}],
                "cancellation_policy": raw["cancellation_policy"],
            },
        ),
        evidence(
            evidence_id=refs[4],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":profiles",
            source_type="HISTORICAL_BEHAVIOR_PROFILE",
            trust_tier="SUPPORTING",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-002 profile context; fraud flags do not replace trip evidence.",
            payload={"rider": raw["rider_profile"], "driver": raw["driver_profile"]},
        ),
    ]
    snapshot = {
        "case_id": case_id,
        "case_version": 1,
        "dispute_type": "NO_SHOW",
        "policy_version": "RYDE_POLICY_V2_1",
        "currency": "SGD",
        "trip_started_at": start_at,
        "trip_ended_at": end_at,
        "claim_text": raw["dispute_ticket"]["description"],
        "disputed_fee_item": "cancellation_fee",
        "disputed_amount_cents": cents(trip["cancellation_fee"]),
        "evidence_refs": refs,
        "created_at": filed_at,
    }
    expected = {
        "case_id": case_id,
        "case_version": 1,
        "business_status": "RESOLVED",
        "matched_rule_ids": ["NS-102"],
        "action": {"type": "NO_ACTION", "fee_item": None, "amount_cents": 0, "currency": "SGD"},
        "official_expected_ruling": "cancellation_charge_upheld",
    }
    return snapshot, records, expected


def build_fare_case(raw: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    case_id = raw["dispute_ticket"]["dispute_id"]
    trip = raw["trip_data"]
    filed_at = raw["dispute_ticket"]["filed_at"]
    start_at = trip["start_time"]
    end_at = trip["end_time"]
    refs = [
        "OFFICIAL-DISP-003-FARE",
        "OFFICIAL-DISP-003-SURGE",
        "OFFICIAL-DISP-003-NOTIFICATION",
        "OFFICIAL-DISP-003-GPS",
        "OFFICIAL-DISP-003-CHAT",
        "OFFICIAL-DISP-003-PROFILES",
    ]
    records = [
        evidence(
            evidence_id=refs[0],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":fare",
            source_type="FARE_LEDGER",
            trust_tier="AUTHORITATIVE",
            observed_at=end_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-003 fare quote and final ledger.",
            payload={
                "currency": "SGD",
                "upfront_quote_cents": cents(trip["upfront_quote"]),
                "actual_fare_cents": cents(trip["actual_fare"]),
                "line_items": [{"fee_item": "surge_differential", "amount_cents": cents(trip["fare_difference"])}],
                "official_fare_breakdown": raw["fare_breakdown"],
            },
        ),
        evidence(
            evidence_id=refs[1],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":surge",
            source_type="SURGE_PRICING_LOG",
            trust_tier="AUTHORITATIVE",
            observed_at=raw["surge_pricing_log"]["surge_activated_at"],
            collected_at=filed_at,
            coverage=coverage(raw["surge_pricing_log"]["surge_activated_at"], start_at, "quote-to-pickup surge transition"),
            provenance_reason="Official hackathon DISP-003 surge pricing log.",
            payload=raw["surge_pricing_log"],
        ),
        evidence(
            evidence_id=refs[2],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":notification",
            source_type="NOTIFICATION_LOG",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(raw["surge_pricing_log"]["surge_activated_at"], start_at, "complete surge-notification eligibility interval"),
            provenance_reason="Official hackathon DISP-003 notification status.",
            payload={
                "rider_notified": raw["surge_pricing_log"]["rider_notified"],
                "notification_method": raw["surge_pricing_log"]["notification_method"],
                "notification_timestamp": raw["surge_pricing_log"]["notification_timestamp"],
            },
        ),
        evidence(
            evidence_id=refs[3],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":gps",
            source_type="PLATFORM_GPS",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "official trip GPS telemetry"),
            provenance_reason="Official hackathon DISP-003 GPS telemetry.",
            payload={"samples": gps_samples(raw["gps_telemetry"])},
        ),
        evidence(
            evidence_id=refs[4],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":chat",
            source_type="AUTHENTICATED_CHAT",
            trust_tier="AUTHORITATIVE",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=coverage(start_at, end_at, "official available trip chat"),
            provenance_reason="Official hackathon DISP-003 authenticated chat.",
            payload={"messages": raw["chat_logs"]},
        ),
        evidence(
            evidence_id=refs[5],
            origin_case_id=case_id,
            source_record_id=trip["trip_id"] + ":profiles",
            source_type="HISTORICAL_BEHAVIOR_PROFILE",
            trust_tier="SUPPORTING",
            observed_at=start_at,
            collected_at=filed_at,
            coverage=None,
            provenance_reason="Official hackathon DISP-003 rider and driver profile context.",
            payload={"rider": raw["rider_profile"], "driver": raw["driver_profile"]},
        ),
    ]
    snapshot = {
        "case_id": case_id,
        "case_version": 1,
        "dispute_type": "FARE_DISPUTE",
        "policy_version": "RYDE_POLICY_V2_1",
        "currency": "SGD",
        "trip_started_at": start_at,
        "trip_ended_at": end_at,
        "claim_text": raw["dispute_ticket"]["description"],
        "disputed_fee_item": "surge_differential",
        "disputed_amount_cents": cents(trip["fare_difference"]),
        "evidence_refs": refs,
        "created_at": filed_at,
    }
    expected = {
        "case_id": case_id,
        "case_version": 1,
        "business_status": "RESOLVED",
        "matched_rule_ids": ["FD-103"],
        "action": {
            "type": "REFUND_DISPUTED_FEE_FULL",
            "fee_item": "surge_differential",
            "amount_cents": 450,
            "currency": "SGD",
        },
        "official_expected_ruling": "full_refund_of_surge_differential",
    }
    return snapshot, records, expected


def policy_payload() -> dict[str, Any]:
    def rule(rule_id: str, dispute: str, priority: int, evaluator: str, parameters: dict[str, Any], outcome: dict[str, Any]) -> dict[str, Any]:
        return {
            "rule_id": rule_id,
            "dispute_type": dispute,
            "priority": priority,
            "evaluator": evaluator,
            "parameters": parameters,
            "allowed_outcome": outcome,
        }

    rules = [
        rule("RD-101", "ROUTE_DEVIATION", 10, "route_v21_required_evidence", {"required_source_types": ["PLATFORM_GPS", "ROUTE_BASELINE", "FARE_LEDGER", "AUTHENTICATED_CHAT", "DEMO_TRAFFIC_FEED"]}, {"business_status": "PENDING_HUMAN_REVIEW"}),
        rule("RD-102", "ROUTE_DEVIATION", 20, "route_v21_within_absolute_tolerance", {"maximum_deviation_m": 1000}, {"action": "NO_ACTION"}),
        rule("RD-103", "ROUTE_DEVIATION", 30, "route_v21_justified_and_notified", {}, {"action": "NO_ACTION"}),
        rule("RD-104", "ROUTE_DEVIATION", 40, "route_v21_justified_not_notified", {"fee_item": "excess_distance_fare"}, {"action": "REFUND_DISPUTED_FEE_PARTIAL"}),
        rule("RD-105", "ROUTE_DEVIATION", 50, "route_v21_unjustified_deviation", {"fee_item": "excess_distance_fare"}, {"action": "REFUND_DISPUTED_FEE_FULL"}),
        rule("RD-106", "ROUTE_DEVIATION", 60, "route_v21_uncertain_material_fact", {}, {"business_status": "PENDING_HUMAN_REVIEW"}),
        rule("NS-101", "NO_SHOW", 10, "no_show_v21_required_evidence", {"required_source_types": ["PLATFORM_GPS", "TRIP_EVENT_LOG", "CONTACT_LOG", "FARE_LEDGER"]}, {"business_status": "PENDING_HUMAN_REVIEW"}),
        rule("NS-102", "NO_SHOW", 20, "no_show_v21_charge_valid", {"fee_cents": 500, "maximum_pickup_distance_m": 150, "minimum_wait_from_scheduled_seconds": 300, "required_contact_channels": ["IN_APP_CHAT", "PHONE"]}, {"action": "NO_ACTION"}),
        rule("NS-103", "NO_SHOW", 30, "no_show_v21_driver_absent", {"fee_item": "cancellation_fee"}, {"action": "REFUND_DISPUTED_FEE_FULL"}),
        rule("NS-104", "NO_SHOW", 40, "no_show_v21_wait_too_short", {"fee_item": "cancellation_fee"}, {"action": "REFUND_DISPUTED_FEE_FULL"}),
        rule("NS-105", "NO_SHOW", 50, "no_show_v21_contact_obligation_failed", {"fee_item": "cancellation_fee"}, {"action": "REFUND_DISPUTED_FEE_FULL"}),
        rule("NS-106", "NO_SHOW", 60, "no_show_v21_conflict_or_incomplete", {}, {"business_status": "PENDING_HUMAN_REVIEW"}),
        rule("FD-101", "FARE_DISPUTE", 10, "fare_v21_required_evidence", {"required_source_types": ["FARE_LEDGER", "SURGE_PRICING_LOG", "NOTIFICATION_LOG"]}, {"business_status": "PENDING_HUMAN_REVIEW"}),
        rule("FD-102", "FARE_DISPUTE", 20, "fare_v21_no_refundable_surge_change", {}, {"action": "NO_ACTION"}),
        rule("FD-103", "FARE_DISPUTE", 30, "fare_v21_unnotified_surge_increase", {"fee_item": "surge_differential"}, {"action": "REFUND_DISPUTED_FEE_FULL"}),
        rule("FD-104", "FARE_DISPUTE", 40, "fare_v21_uncertain_or_conflicting", {}, {"business_status": "PENDING_HUMAN_REVIEW"}),
    ]
    return {
        "policy_id": "RYDE_DISPUTE_RESOLUTION_POLICY",
        "policy_version": "RYDE_POLICY_V2_1",
        "effective_from": "2026-01-01T00:00:00+08:00",
        "effective_to": None,
        "timezone": "Asia/Singapore",
        "rules": rules,
        "precedents": [
            {"precedent_id": "RYDE-V2.1-7.1", "dispute_type": "ROUTE_DEVIATION", "rule_ids": ["RD-104"], "outcome": "PARTIAL_REFUND_EXCESS_DISTANCE_FARE", "amount_cents": 320, "authority": "ADVISORY_ONLY"},
            {"precedent_id": "RYDE-V2.1-7.2", "dispute_type": "FARE_DISPUTE", "rule_ids": ["FD-103"], "outcome": "REFUND_SURGE_DIFFERENTIAL", "amount_cents": 320, "authority": "ADVISORY_ONLY"},
            {"precedent_id": "RYDE-V2.1-7.3", "dispute_type": "NO_SHOW", "rule_ids": ["NS-105"], "outcome": "REFUND_CANCELLATION_FEE", "amount_cents": 500, "authority": "ADVISORY_ONLY"},
        ],
    }


def find_source(directory: Path, contains: str) -> Path:
    matches = [path for path in directory.glob("*.md") if contains in path.name]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one source containing {contains!r}; got {matches}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_dir", nargs="?", type=Path, default=OFFICIAL_SOURCE_DIR)
    args = parser.parse_args()
    source_dir = args.source_dir.resolve()
    source_files = {
        "route": find_source(source_dir, "Route Deviation"),
        "no_show": find_source(source_dir, "No-Show"),
        "fare": find_source(source_dir, "Fare Dispute"),
        "policy": find_source(source_dir, "Policy v2.1"),
    }

    OFFICIAL_SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    archived: dict[str, Path] = {}
    for key, source in source_files.items():
        target = OFFICIAL_SOURCE_DIR / source.name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        archived[key] = target

    route = extract_json(archived["route"])
    no_show = extract_json(archived["no_show"])
    fare = extract_json(archived["fare"])
    built = [build_route_case(route), build_no_show_case(no_show), build_fare_case(fare)]
    payload = {
        "dataset_id": "RIDERESOLVE_OFFICIAL_HACKATHON_SAMPLES_2026_V1",
        "synthetic": True,
        "source_kind": "OFFICIAL_HACKATHON_SAMPLE_DATASET",
        "precedence": "OFFICIAL_VALUES_OVERRIDE_CONFLICTING_MOCK_VALUES",
        "policy_version": "RYDE_POLICY_V2_1",
        "cases": [item[0] for item in built],
        "evidence": [record for item in built for record in item[1]],
        "expected_results": [item[2] for item in built],
    }
    CASE_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CASE_OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    POLICY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    POLICY_OUTPUT.write_text(json.dumps(policy_payload(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {
        "source_kind": "OFFICIAL_HACKATHON_SAMPLE_DATASET",
        "precedence": "OFFICIAL_VALUES_OVERRIDE_CONFLICTING_MOCK_VALUES",
        "files": [
            {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in archived.values()
        ],
    }
    MANIFEST_OUTPUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(CASE_OUTPUT)
    print(POLICY_OUTPUT)
    print(MANIFEST_OUTPUT)


if __name__ == "__main__":
    main()
