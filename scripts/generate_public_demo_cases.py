from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from rideresolve.integrity import compute_evidence_checksum
from rideresolve.models import CaseSnapshot, Evidence
from rideresolve.policy import evaluate_case, load_policy


ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PATH = ROOT / "data" / "cases" / "official_cases.json"
OUTPUT_PATH = ROOT / "data" / "cases" / "synthetic_demo_cases.json"
POLICY_PATH = ROOT / "data" / "policies" / "RYDE_POLICY_V2_1.json"


Mutation = Callable[[dict[str, Any], dict[str, dict[str, Any]]], None]


def set_line_item(evidence: dict[str, Any], fee_item: str, amount_cents: int) -> None:
    for item in evidence["payload"].get("line_items", []):
        if item.get("fee_item") == fee_item:
            item["amount_cents"] = amount_cents
            return
    raise ValueError(f"missing line item: {fee_item}")


def route_notified(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    by_type["DEMO_TRAFFIC_FEED"]["payload"]["reroute_justified"] = True
    by_type["AUTHENTICATED_CHAT"]["payload"]["route_notification_sent"] = True
    by_type["AUTHENTICATED_CHAT"]["payload"]["verbal_notification_verified"] = False


def route_unjustified(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    case["disputed_fee_item"] = "excess_distance_fare"
    case["disputed_amount_cents"] = 380
    by_type["DEMO_TRAFFIC_FEED"]["payload"]["reroute_justified"] = False
    by_type["AUTHENTICATED_CHAT"]["payload"]["route_notification_sent"] = False
    by_type["AUTHENTICATED_CHAT"]["payload"]["verbal_notification_verified"] = False
    set_line_item(by_type["FARE_LEDGER"], "excess_distance_fare", 380)


def route_missing_gps(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    by_type.pop("PLATFORM_GPS")


def no_show_driver_far(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    by_type["PLATFORM_GPS"]["payload"]["arrival_distance_m"] = 420


def no_show_short_wait(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    by_type["TRIP_EVENT_LOG"]["payload"]["cancelled_at"] = "2026-09-13T08:48:00+08:00"


def no_show_missing_phone(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    contact = by_type["CONTACT_LOG"]["payload"]
    contact["attempts"] = [
        item for item in contact.get("attempts", []) if item.get("channel") != "PHONE"
    ]


def fare_notified(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    notice = by_type["NOTIFICATION_LOG"]["payload"]
    notice["rider_notified"] = True
    notice["notification_method"] = "IN_APP_CONFIRMATION"
    notice["notification_timestamp"] = "2026-09-14T21:04:45+08:00"


def fare_unnotified(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    case["disputed_amount_cents"] = 525
    ledger = by_type["FARE_LEDGER"]
    set_line_item(ledger, "surge_differential", 525)


def fare_missing_notice(case: dict[str, Any], by_type: dict[str, dict[str, Any]]) -> None:
    by_type.pop("NOTIFICATION_LOG")


SCENARIOS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "DEMO-101",
        "trip_reference": "TRIP-2026-20101",
        "source_case_id": "DISP-001",
        "title": "Traffic detour disclosed to rider",
        "claim": "The route was longer, but the driver warned me about a verified road closure.",
        "mutation": route_notified,
    },
    {
        "case_id": "DEMO-102",
        "trip_reference": "TRIP-2026-20102",
        "source_case_id": "DISP-001",
        "title": "Unjustified longer route",
        "claim": "The driver took an unexplained longer route and I was charged extra distance fare.",
        "mutation": route_unjustified,
    },
    {
        "case_id": "DEMO-103",
        "trip_reference": "TRIP-2026-20103",
        "source_case_id": "DISP-001",
        "title": "Incomplete route GPS",
        "claim": "The trip was longer than expected, but part of the platform GPS record is missing.",
        "mutation": route_missing_gps,
    },
    {
        "case_id": "DEMO-201",
        "trip_reference": "TRIP-2026-20201",
        "source_case_id": "DISP-002",
        "title": "Driver marked arrival too far away",
        "claim": "The driver marked arrival far from the pickup point and I was charged a no-show fee.",
        "mutation": no_show_driver_far,
    },
    {
        "case_id": "DEMO-202",
        "trip_reference": "TRIP-2026-20202",
        "source_case_id": "DISP-002",
        "title": "Driver cancelled before minimum wait",
        "claim": "The driver cancelled before the required waiting period and I was charged a no-show fee.",
        "mutation": no_show_short_wait,
    },
    {
        "case_id": "DEMO-203",
        "trip_reference": "TRIP-2026-20203",
        "source_case_id": "DISP-002",
        "title": "Required contact channel missing",
        "claim": "The driver did not call me before cancelling and I was charged a no-show fee.",
        "mutation": no_show_missing_phone,
    },
    {
        "case_id": "DEMO-301",
        "trip_reference": "TRIP-2026-20301",
        "source_case_id": "DISP-003",
        "title": "Surge increase accepted after notice",
        "claim": "The fare increased because of surge pricing, and the change was shown before pickup.",
        "mutation": fare_notified,
    },
    {
        "case_id": "DEMO-302",
        "trip_reference": "TRIP-2026-20302",
        "source_case_id": "DISP-003",
        "title": "Unnotified surge increase",
        "claim": "The final fare was higher than the quote because of an unannounced surge increase.",
        "mutation": fare_unnotified,
    },
    {
        "case_id": "DEMO-303",
        "trip_reference": "TRIP-2026-20303",
        "source_case_id": "DISP-003",
        "title": "Missing fare notification record",
        "claim": "The fare increased, but the notification record is unavailable and needs review.",
        "mutation": fare_missing_notice,
    },
)


def build_scenario(
    scenario: dict[str, Any],
    cases_by_id: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    source_case = copy.deepcopy(cases_by_id[scenario["source_case_id"]])
    source_items = [copy.deepcopy(evidence_by_id[item]) for item in source_case["evidence_refs"]]
    by_type = {item["source_type"]: item for item in source_items}

    case_id = scenario["case_id"]
    trip_reference = scenario["trip_reference"]
    source_case["case_id"] = case_id
    source_case["claim_text"] = f"[SYNTHETIC DEMO] {scenario['claim']}"
    scenario["mutation"](source_case, by_type)

    output_items: list[dict[str, Any]] = []
    evidence_refs: list[str] = []
    for source_type, item in by_type.items():
        suffix = source_type.replace("_", "-")
        evidence_id = f"SYNTHETIC-{case_id}-{suffix}"
        old_id = item["evidence_id"]
        item["evidence_id"] = evidence_id
        item["origin_case_id"] = case_id
        source_suffix = item["source_record_id"].split(":", 1)[1]
        item["source_record_id"] = f"{trip_reference}:{source_suffix}"
        item["related_evidence_ids"] = [
            value.replace(old_id, evidence_id) for value in item.get("related_evidence_ids", [])
        ]
        item["provenance_reason"] = (
            f"Synthetic public demo fixture for {scenario['title']}; "
            "not an official, production, or real-person record."
        )
        if item.get("coverage"):
            item["coverage"]["scope"] = f"synthetic demo coverage for {scenario['title']}"
        item["payload"].pop("official_evidence_complete", None)
        item["payload"].pop("official_fare_breakdown", None)
        candidate = Evidence.model_validate({**item, "checksum": ""})
        item["checksum"] = compute_evidence_checksum(candidate)
        Evidence.model_validate(item)
        evidence_refs.append(evidence_id)
        output_items.append(item)

    source_case["evidence_refs"] = evidence_refs
    CaseSnapshot.model_validate(source_case)
    return source_case, output_items


def main() -> None:
    official = json.loads(OFFICIAL_PATH.read_text(encoding="utf-8"))
    cases_by_id = {item["case_id"]: item for item in official["cases"]}
    evidence_by_id = {item["evidence_id"]: item for item in official["evidence"]}
    cases: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    catalog: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        case, items = build_scenario(scenario, cases_by_id, evidence_by_id)
        cases.append(case)
        evidence.extend(items)
        catalog.append(
            {
                "case_id": scenario["case_id"],
                "trip_reference": scenario["trip_reference"],
                "title": scenario["title"],
            }
        )

    policy = load_policy(POLICY_PATH)
    evidence_models = [Evidence.model_validate(item) for item in evidence]
    expected_results: list[dict[str, Any]] = []
    for item in cases:
        snapshot = CaseSnapshot.model_validate(item)
        result = evaluate_case(snapshot, evidence_models, policy)
        expected_results.append(
            {
                "case_id": snapshot.case_id,
                "case_version": snapshot.case_version,
                "business_status": result.business_status.value,
                "matched_rule_ids": list(result.matched_rule_ids),
                "action": (
                    result.allowed_action.model_dump(mode="json")
                    if result.allowed_action is not None
                    else None
                ),
            }
        )

    dataset = {
        "dataset_id": "RIDERESOLVE_SYNTHETIC_PUBLIC_DEMOS_V1",
        "source_kind": "SYNTHETIC_PUBLIC_DEMO_DATASET",
        "synthetic": True,
        "disclaimer": (
            "All records are fictional demonstration fixtures. Official hackathon data is stored "
            "separately and takes precedence over synthetic records on any identity conflict."
        ),
        "catalog": catalog,
        "cases": cases,
        "evidence": evidence,
        "expected_results": expected_results,
    }
    OUTPUT_PATH.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
