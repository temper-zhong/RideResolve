from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from rideresolve.gps import haversine_m
from rideresolve.integrity import compute_evidence_checksum
from rideresolve.models import (
    CaseSnapshot,
    Coverage,
    DisputeType,
    Evidence,
    SourceType,
    TrustTier,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "cases" / "tool_cases.json"
SGT = timezone(timedelta(hours=8))
START = datetime(2026, 10, 6, 9, 0, tzinfo=SGT)
END = START + timedelta(minutes=10)


def make_evidence(
    evidence_id: str,
    case_id: str,
    source_type: SourceType,
    payload: dict,
    *,
    trust_tier: TrustTier = TrustTier.AUTHORITATIVE,
    coverage: Coverage | None = None,
) -> Evidence:
    item = Evidence(
        evidence_id=evidence_id,
        origin_case_id=case_id,
        source_record_id=f"SRC-{evidence_id}",
        source_type=source_type,
        trust_tier=trust_tier,
        observed_at=START,
        collected_at=END,
        coverage=coverage,
        provenance_reason="Synthetic RideResolve Gate A fixture",
        payload=payload,
        checksum="",
    )
    return item.model_copy(update={"checksum": compute_evidence_checksum(item)})


def route_case() -> tuple[CaseSnapshot, list[Evidence]]:
    case_id = "CASE-RD-TOOL-001"
    samples = [
        {
            "timestamp": (START + timedelta(minutes=index)).isoformat(),
            "latitude": 1.3000,
            "longitude": 103.8000 + 0.0100 * index,
        }
        for index in range(11)
    ]
    distance_m = sum(
        haversine_m(
            left["latitude"],
            left["longitude"],
            right["latitude"],
            right["longitude"],
        )
        for left, right in zip(samples, samples[1:])
    )
    full_trip = Coverage(start_at=START, end_at=END, is_complete=True, scope="trip")
    evidence = [
        make_evidence(
            "EV-RD-GPS-FULL",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples},
            coverage=full_trip,
        ),
        make_evidence(
            "EV-RD-BASELINE",
            case_id,
            SourceType.ROUTE_BASELINE,
            {"baseline_distance_m": distance_m / 1.30},
        ),
        make_evidence(
            "EV-RD-FARE",
            case_id,
            SourceType.FARE_LEDGER,
            {
                "currency": "SGD",
                "line_items": [
                    {"fee_item": "distance_surcharge", "amount_cents": 325}
                ],
                "total_paid_cents": 2480,
            },
        ),
        make_evidence(
            "EV-RD-CHAT",
            case_id,
            SourceType.AUTHENTICATED_CHAT,
            {"messages": []},
            trust_tier=TrustTier.SUPPORTING,
            coverage=Coverage(
                start_at=START,
                end_at=END,
                is_complete=True,
                scope="platform-trip-chat",
            ),
        ),
        make_evidence(
            "EV-RD-TRAFFIC",
            case_id,
            SourceType.DEMO_TRAFFIC_FEED,
            {"events": []},
            trust_tier=TrustTier.SUPPORTING,
            coverage=Coverage(
                start_at=START,
                end_at=END,
                is_complete=True,
                scope="trip-corridor",
            ),
        ),
    ]
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=1,
        dispute_type=DisputeType.ROUTE_DEVIATION,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=START,
        trip_ended_at=END,
        claim_text="The driver took a longer route and I was overcharged.",
        disputed_fee_item="distance_surcharge",
        disputed_amount_cents=325,
        evidence_refs=tuple(item.evidence_id for item in evidence),
        created_at=END + timedelta(minutes=1),
    )
    return snapshot, evidence


def no_show_case() -> tuple[CaseSnapshot, list[Evidence]]:
    case_id = "CASE-NS-TOOL-001"
    arrived_at = START
    cancelled_at = START + timedelta(minutes=6)
    evidence = [
        make_evidence(
            "EV-NS-GPS",
            case_id,
            SourceType.PLATFORM_GPS,
            {"arrival_distance_m": 100},
        ),
        make_evidence(
            "EV-NS-EVENT",
            case_id,
            SourceType.TRIP_EVENT_LOG,
            {
                "arrived_at": arrived_at.isoformat(),
                "cancelled_at": cancelled_at.isoformat(),
                "cancelled_by": "RIDER",
            },
        ),
        make_evidence(
            "EV-NS-CONTACT",
            case_id,
            SourceType.CONTACT_LOG,
            {
                "attempts": [
                    {
                        "channel": "IN_APP",
                        "at": (START + timedelta(minutes=1)).isoformat(),
                    }
                ]
            },
            coverage=Coverage(
                start_at=arrived_at,
                end_at=cancelled_at,
                is_complete=True,
                scope="arrival-to-cancellation",
            ),
        ),
        make_evidence(
            "EV-NS-FARE",
            case_id,
            SourceType.FARE_LEDGER,
            {
                "currency": "SGD",
                "line_items": [
                    {"fee_item": "cancellation_fee", "amount_cents": 400}
                ],
                "total_paid_cents": 400,
            },
        ),
    ]
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=1,
        dispute_type=DisputeType.NO_SHOW,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=START,
        trip_ended_at=END,
        claim_text="The driver did not show up but I was charged a cancellation fee.",
        disputed_fee_item="cancellation_fee",
        disputed_amount_cents=400,
        evidence_refs=tuple(item.evidence_id for item in evidence),
        created_at=END + timedelta(minutes=1),
    )
    return snapshot, evidence


def main() -> None:
    cases: list[CaseSnapshot] = []
    evidence: list[Evidence] = []
    for builder in (route_case, no_show_case):
        snapshot, items = builder()
        cases.append(snapshot)
        evidence.extend(items)
    payload = {
        "dataset_id": "RIDERESOLVE_SYNTHETIC_GATE_A_V1",
        "synthetic": True,
        "cases": [case.model_dump(mode="json") for case in cases],
        "evidence": [item.model_dump(mode="json") for item in evidence],
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(OUTPUT)


if __name__ == "__main__":
    main()
