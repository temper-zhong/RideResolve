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
    RecordRole,
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
    record_role: RecordRole = RecordRole.ORIGINAL,
    related_evidence_ids: tuple[str, ...] = (),
    provenance_reason: str = "Synthetic RideResolve Gate A fixture",
    observed_at: datetime = START,
    collected_at: datetime = END,
) -> Evidence:
    item = Evidence(
        evidence_id=evidence_id,
        origin_case_id=case_id,
        source_record_id=f"SRC-{evidence_id}",
        source_type=source_type,
        trust_tier=trust_tier,
        observed_at=observed_at,
        collected_at=collected_at,
        coverage=coverage,
        record_role=record_role,
        related_evidence_ids=related_evidence_ids,
        provenance_reason=provenance_reason,
        payload=payload,
        checksum="",
    )
    return item.model_copy(update={"checksum": compute_evidence_checksum(item)})


def make_history_profile(evidence_id: str, case_id: str) -> Evidence:
    """Create non-decisional synthetic context for both parties."""
    return make_evidence(
        evidence_id,
        case_id,
        SourceType.HISTORICAL_BEHAVIOR_PROFILE,
        {
            "decision_use": "CONTEXT_ONLY",
            "profiles": [
                {
                    "party": "RIDER",
                    "account_age_days": 620,
                    "completed_trips": 148,
                    "prior_disputes_180d": 1,
                    "rating_pattern": "STABLE",
                },
                {
                    "party": "DRIVER",
                    "account_age_days": 910,
                    "completed_trips": 2310,
                    "prior_disputes_180d": 2,
                    "rating_pattern": "STABLE",
                },
            ],
        },
        trust_tier=TrustTier.SUPPORTING,
        provenance_reason=(
            "Synthetic historical profile for contextual pattern review only; "
            "excluded from policy, status, liability, and money decisions"
        ),
    )


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
            {
                "messages": [
                    {
                        "message_id": "MSG-RD-001",
                        "sender": "RIDER",
                        "text": "Please follow the suggested route. I do not agree to an extra stop.",
                        "tag": "ROUTE_PREFERENCE",
                        "synthetic_semantic_labels": {
                            "sentiment": "CONCERNED",
                            "consent": "DENIED_FOR_EXTRA_STOP",
                            "disagreement": True,
                            "threat": False,
                        },
                    },
                    {
                        "message_id": "MSG-RD-002",
                        "sender": "DRIVER",
                        "text": "Traffic is slow ahead; I may need a detour.",
                        "tag": "DETOUR_NOTICE",
                        "synthetic_semantic_labels": {
                            "sentiment": "NEUTRAL",
                            "consent": "NOT_APPLICABLE",
                            "disagreement": False,
                            "threat": False,
                        },
                    },
                ]
            },
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
        make_history_profile("EV-RD-HISTORY", case_id),
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


def fixture_route_case(
    case_key: str,
    *,
    start: datetime,
    ratio: float,
    amount_cents: int,
    claim_text: str,
    incomplete_gps: bool = False,
    road_closure: bool = False,
    chat_complete: bool = True,
    traffic_complete: bool = True,
    oral_stop_claim: bool = False,
) -> tuple[CaseSnapshot, list[Evidence]]:
    """Materialize one auditable route fixture outside the test suite."""
    case_id = f"CASE-{case_key}"
    end = start + timedelta(minutes=10)
    prefix = f"EV-{case_key}"
    samples = [
        {
            "timestamp": (start + timedelta(minutes=index)).isoformat(),
            "latitude": 1.3000,
            "longitude": 103.8000 + 0.0100 * index,
        }
        for index in range(11)
    ]
    actual_distance_m = sum(
        haversine_m(
            left["latitude"],
            left["longitude"],
            right["latitude"],
            right["longitude"],
        )
        for left, right in zip(samples, samples[1:])
    )
    full_coverage = Coverage(
        start_at=start,
        end_at=end,
        is_complete=True,
        scope="trip",
    )
    items: list[Evidence] = []
    if incomplete_gps:
        segment_coverage = Coverage(
            start_at=start,
            end_at=end,
            is_complete=False,
            scope="trip-segment",
        )
        items.extend(
            [
                make_evidence(
                    f"{prefix}-GPS-A",
                    case_id,
                    SourceType.PLATFORM_GPS,
                    {"samples": samples[:3]},
                    coverage=segment_coverage,
                    observed_at=start,
                    collected_at=end,
                ),
                make_evidence(
                    f"{prefix}-GPS-B",
                    case_id,
                    SourceType.PLATFORM_GPS,
                    {"samples": samples[5:]},
                    coverage=segment_coverage,
                    observed_at=start,
                    collected_at=end,
                ),
            ]
        )
    else:
        items.append(
            make_evidence(
                f"{prefix}-GPS",
                case_id,
                SourceType.PLATFORM_GPS,
                {"samples": samples},
                coverage=full_coverage,
                observed_at=start,
                collected_at=end,
            )
        )

    items.extend(
        [
            make_evidence(
                f"{prefix}-BASELINE",
                case_id,
                SourceType.ROUTE_BASELINE,
                {"baseline_distance_m": actual_distance_m / ratio},
                observed_at=start,
                collected_at=end,
            ),
            make_evidence(
                f"{prefix}-FARE",
                case_id,
                SourceType.FARE_LEDGER,
                {
                    "currency": "SGD",
                    "line_items": [
                        {
                            "fee_item": "distance_surcharge",
                            "amount_cents": amount_cents,
                        }
                    ],
                    "total_paid_cents": 2000 + amount_cents,
                },
                observed_at=start,
                collected_at=end,
            ),
            make_evidence(
                f"{prefix}-CHAT",
                case_id,
                SourceType.AUTHENTICATED_CHAT,
                {"messages": []},
                trust_tier=TrustTier.SUPPORTING,
                coverage=Coverage(
                    start_at=start,
                    end_at=end,
                    is_complete=chat_complete,
                    scope="platform-trip-chat",
                ),
                observed_at=start,
                collected_at=end,
            ),
            make_evidence(
                f"{prefix}-TRAFFIC",
                case_id,
                SourceType.DEMO_TRAFFIC_FEED,
                {
                    "events": (
                        [{"type": "ROAD_CLOSURE", "relevant": True}]
                        if road_closure
                        else []
                    )
                },
                trust_tier=TrustTier.SUPPORTING,
                coverage=Coverage(
                    start_at=start,
                    end_at=end,
                    is_complete=traffic_complete,
                    scope="trip-corridor",
                ),
                observed_at=start,
                collected_at=end,
            ),
        ]
    )
    if oral_stop_claim:
        items.append(
            make_evidence(
                f"{prefix}-STATEMENT",
                case_id,
                SourceType.PARTY_STATEMENT,
                {
                    "party": "DRIVER",
                    "claims_oral_stop_request": True,
                    "statement": "The rider asked verbally for an unscheduled stop.",
                },
                trust_tier=TrustTier.CLAIM,
                observed_at=start,
                collected_at=end,
            )
        )
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=1,
        dispute_type=DisputeType.ROUTE_DEVIATION,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=start,
        trip_ended_at=end,
        claim_text=claim_text,
        disputed_fee_item="distance_surcharge",
        disputed_amount_cents=amount_cents,
        evidence_refs=tuple(item.evidence_id for item in items),
        created_at=end + timedelta(minutes=1),
    )
    return snapshot, items


def fixture_no_show_case(
    case_key: str,
    *,
    start: datetime,
    distance_m: float,
    wait_seconds: int,
    amount_cents: int,
    claim_text: str,
    contact_complete: bool = True,
    has_contact_attempt: bool = True,
    missing_source: SourceType | None = None,
    conflicting_distance_m: float | None = None,
) -> tuple[CaseSnapshot, list[Evidence]]:
    """Materialize one auditable no-show fixture outside the test suite."""
    case_id = f"CASE-{case_key}"
    end = start + timedelta(minutes=10)
    cancelled_at = start + timedelta(seconds=wait_seconds)
    prefix = f"EV-{case_key}"
    items: list[Evidence] = []

    if missing_source != SourceType.PLATFORM_GPS:
        items.append(
            make_evidence(
                f"{prefix}-GPS-A",
                case_id,
                SourceType.PLATFORM_GPS,
                {"arrival_distance_m": distance_m},
                observed_at=start,
                collected_at=end,
            )
        )
        if conflicting_distance_m is not None:
            items.append(
                make_evidence(
                    f"{prefix}-GPS-B",
                    case_id,
                    SourceType.PLATFORM_GPS,
                    {"arrival_distance_m": conflicting_distance_m},
                    observed_at=start + timedelta(seconds=5),
                    collected_at=end,
                    provenance_reason=(
                        "Synthetic second authoritative GPS observation for conflict testing"
                    ),
                )
            )
    if missing_source != SourceType.TRIP_EVENT_LOG:
        items.append(
            make_evidence(
                f"{prefix}-EVENT",
                case_id,
                SourceType.TRIP_EVENT_LOG,
                {
                    "arrived_at": start.isoformat(),
                    "cancelled_at": cancelled_at.isoformat(),
                    "cancelled_by": "RIDER",
                },
                observed_at=start,
                collected_at=end,
            )
        )
    if missing_source != SourceType.CONTACT_LOG:
        attempts = (
            [
                {
                    "channel": "IN_APP",
                    "at": (start + timedelta(seconds=60)).isoformat(),
                }
            ]
            if has_contact_attempt
            else []
        )
        items.append(
            make_evidence(
                f"{prefix}-CONTACT",
                case_id,
                SourceType.CONTACT_LOG,
                {"attempts": attempts},
                coverage=Coverage(
                    start_at=start,
                    end_at=cancelled_at,
                    is_complete=contact_complete,
                    scope="arrival-to-cancellation",
                ),
                observed_at=start,
                collected_at=end,
            )
        )
    if missing_source != SourceType.FARE_LEDGER:
        items.append(
            make_evidence(
                f"{prefix}-FARE",
                case_id,
                SourceType.FARE_LEDGER,
                {
                    "currency": "SGD",
                    "line_items": [
                        {
                            "fee_item": "cancellation_fee",
                            "amount_cents": amount_cents,
                        }
                    ],
                    "total_paid_cents": amount_cents,
                },
                observed_at=start,
                collected_at=end,
            )
        )
    snapshot = CaseSnapshot(
        case_id=case_id,
        case_version=1,
        dispute_type=DisputeType.NO_SHOW,
        policy_version="DEMO_POLICY_V1",
        currency="SGD",
        trip_started_at=start,
        trip_ended_at=end,
        claim_text=claim_text,
        disputed_fee_item="cancellation_fee",
        disputed_amount_cents=amount_cents,
        evidence_refs=tuple(item.evidence_id for item in items),
        created_at=end + timedelta(minutes=1),
    )
    return snapshot, items


def expanded_fixture_cases() -> list[tuple[CaseSnapshot, list[Evidence]]]:
    """Promote Gate B fixtures and add the five previously uncovered rules."""
    return [
        fixture_route_case(
            "RD_UNJUSTIFIED_DEVIATION",
            start=datetime(2026, 9, 18, 18, 40, tzinfo=SGT),
            ratio=1.30,
            amount_cents=280,
            claim_text="The trip was substantially longer and included an unexplained surcharge.",
        ),
        fixture_route_case(
            "RD_VERIFIED_ROAD_CLOSURE",
            start=datetime(2026, 9, 21, 23, 15, tzinfo=SGT),
            ratio=1.27,
            amount_cents=510,
            claim_text="The route changed during a late-night road closure.",
            road_closure=True,
        ),
        fixture_route_case(
            "RD_INCOMPLETE_GPS",
            start=datetime(2026, 9, 25, 7, 5, tzinfo=SGT),
            ratio=1.24,
            amount_cents=190,
            claim_text="Part of the route trace is missing and the extra distance is disputed.",
            incomplete_gps=True,
        ),
        fixture_route_case(
            "RD_BOUNDARY_20_PERCENT",
            start=datetime(2026, 9, 28, 12, 20, tzinfo=SGT),
            ratio=1.20,
            amount_cents=235,
            claim_text="The measured route is exactly at the allowed deviation threshold.",
        ),
        fixture_route_case(
            "RD_UNCERTAIN_EXCEPTION",
            start=datetime(2026, 10, 1, 17, 55, tzinfo=SGT),
            ratio=1.26,
            amount_cents=365,
            claim_text="A detour may have been necessary, but the exception channel is incomplete.",
            traffic_complete=False,
        ),
        fixture_route_case(
            "RD_UNVERIFIABLE_ORAL_CLAIM",
            start=datetime(2026, 10, 3, 0, 25, tzinfo=SGT),
            ratio=1.23,
            amount_cents=445,
            claim_text="The driver says I requested a stop verbally; I dispute that account.",
            oral_stop_claim=True,
        ),
        fixture_no_show_case(
            "NS_VALID_CHARGE",
            start=datetime(2026, 9, 17, 8, 10, tzinfo=SGT),
            distance_m=100,
            wait_seconds=360,
            amount_cents=360,
            claim_text="I was charged after the driver waited near the pickup point.",
        ),
        fixture_no_show_case(
            "NS_DRIVER_TOO_FAR",
            start=datetime(2026, 9, 20, 19, 35, tzinfo=SGT),
            distance_m=300,
            wait_seconds=360,
            amount_cents=420,
            claim_text="The driver marked arrival while still far from the pickup point.",
        ),
        fixture_no_show_case(
            "NS_WAIT_TOO_SHORT",
            start=datetime(2026, 9, 23, 14, 45, tzinfo=SGT),
            distance_m=110,
            wait_seconds=120,
            amount_cents=275,
            claim_text="The driver cancelled before the required waiting period elapsed.",
        ),
        fixture_no_show_case(
            "NS_CONTACT_COVERAGE_INCOMPLETE",
            start=datetime(2026, 9, 27, 2, 5, tzinfo=SGT),
            distance_m=125,
            wait_seconds=330,
            amount_cents=390,
            claim_text="The contact history is incomplete for part of the waiting interval.",
            contact_complete=False,
            has_contact_attempt=False,
        ),
        fixture_no_show_case(
            "NS_MISSING_REQUIRED_EVIDENCE",
            start=datetime(2026, 9, 30, 6, 30, tzinfo=SGT),
            distance_m=95,
            wait_seconds=340,
            amount_cents=315,
            claim_text="The cancellation fee is disputed, but the contact log is unavailable.",
            missing_source=SourceType.CONTACT_LOG,
        ),
        fixture_no_show_case(
            "NS_NO_PLATFORM_CONTACT",
            start=datetime(2026, 10, 2, 21, 50, tzinfo=SGT),
            distance_m=120,
            wait_seconds=320,
            amount_cents=465,
            claim_text="The driver waited nearby but made no in-app contact attempt.",
            has_contact_attempt=False,
        ),
        fixture_no_show_case(
            "NS_AUTHORITATIVE_CONFLICT",
            start=datetime(2026, 10, 4, 10, 15, tzinfo=SGT),
            distance_m=80,
            conflicting_distance_m=260,
            wait_seconds=350,
            amount_cents=340,
            claim_text="Two authoritative location records disagree about the arrival position.",
        ),
    ]


def route_delta_cases() -> tuple[list[CaseSnapshot], list[Evidence]]:
    """Create the persisted v1/v2 pair used by the Decision Delta demo."""
    case_id = "CASE-RD-001"
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
    segment_coverage = Coverage(
        start_at=START,
        end_at=END,
        is_complete=False,
        scope="trip-segment",
    )
    evidence = [
        make_evidence(
            "EV-RD-001-GPS-A",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples[:3]},
            coverage=segment_coverage,
            provenance_reason="Synthetic original platform GPS segment for Decision Delta",
        ),
        make_evidence(
            "EV-RD-001-GPS-B",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples[5:]},
            coverage=segment_coverage,
            provenance_reason="Synthetic original platform GPS segment for Decision Delta",
        ),
        make_evidence(
            "EV-RD-001-BASELINE",
            case_id,
            SourceType.ROUTE_BASELINE,
            {"baseline_distance_m": distance_m / 1.30},
            provenance_reason="Synthetic route baseline for Decision Delta",
        ),
        make_evidence(
            "EV-RD-001-FARE",
            case_id,
            SourceType.FARE_LEDGER,
            {
                "currency": "SGD",
                "line_items": [
                    {"fee_item": "distance_surcharge", "amount_cents": 325}
                ],
                "total_paid_cents": 2480,
            },
            provenance_reason="Synthetic authoritative fare ledger for Decision Delta",
        ),
        make_evidence(
            "EV-RD-001-CHAT",
            case_id,
            SourceType.AUTHENTICATED_CHAT,
            {
                "messages": [
                    {
                        "message_id": "MSG-RD-DELTA-001",
                        "sender": "RIDER",
                        "text": "Please follow the suggested route. I do not agree to an extra stop.",
                        "tag": "ROUTE_PREFERENCE",
                        "synthetic_semantic_labels": {
                            "sentiment": "CONCERNED",
                            "consent": "DENIED_FOR_EXTRA_STOP",
                            "disagreement": True,
                            "threat": False,
                        },
                    },
                    {
                        "message_id": "MSG-RD-DELTA-002",
                        "sender": "DRIVER",
                        "text": "Traffic is slow ahead; I may need a detour.",
                        "tag": "DETOUR_NOTICE",
                        "synthetic_semantic_labels": {
                            "sentiment": "NEUTRAL",
                            "consent": "NOT_APPLICABLE",
                            "disagreement": False,
                            "threat": False,
                        },
                    },
                ]
            },
            trust_tier=TrustTier.SUPPORTING,
            coverage=Coverage(
                start_at=START,
                end_at=END,
                is_complete=True,
                scope="platform-trip-chat",
            ),
            provenance_reason="Synthetic complete in-platform chat record for Decision Delta",
        ),
        make_evidence(
            "EV-RD-001-TRAFFIC",
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
            provenance_reason="Synthetic complete traffic feed for Decision Delta",
        ),
        make_history_profile("EV-RD-001-HISTORY", case_id),
        make_evidence(
            "EV-RD-GPS-SUPPLEMENT",
            case_id,
            SourceType.PLATFORM_GPS,
            {"samples": samples[3:5]},
            coverage=Coverage(
                start_at=START + timedelta(minutes=3),
                end_at=START + timedelta(minutes=4),
                is_complete=True,
                scope="missing-trip-segment",
            ),
            record_role=RecordRole.SUPPLEMENT,
            related_evidence_ids=("EV-RD-001-GPS-A", "EV-RD-001-GPS-B"),
            provenance_reason="Synthetic late-arriving authoritative GPS supplement for Decision Delta",
        ),
    ]
    original_refs = tuple(item.evidence_id for item in evidence[:-1])
    common = {
        "case_id": case_id,
        "dispute_type": DisputeType.ROUTE_DEVIATION,
        "policy_version": "DEMO_POLICY_V1",
        "currency": "SGD",
        "trip_started_at": START,
        "trip_ended_at": END,
        "claim_text": "The driver took a longer route and I was overcharged.",
        "disputed_fee_item": "distance_surcharge",
        "disputed_amount_cents": 325,
    }
    before = CaseSnapshot(
        **common,
        case_version=1,
        evidence_refs=original_refs,
        created_at=END + timedelta(minutes=1),
    )
    after = CaseSnapshot(
        **common,
        case_version=2,
        evidence_refs=original_refs + ("EV-RD-GPS-SUPPLEMENT",),
        created_at=END + timedelta(minutes=2),
    )
    return [before, after], evidence


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
        make_history_profile("EV-NS-HISTORY", case_id),
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
    delta_snapshots, delta_evidence = route_delta_cases()
    cases.extend(delta_snapshots)
    evidence.extend(delta_evidence)
    for snapshot, items in expanded_fixture_cases():
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
