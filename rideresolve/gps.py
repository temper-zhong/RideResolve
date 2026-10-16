from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import asin, cos, radians, sin, sqrt
from typing import Iterable

from pydantic import BaseModel, ConfigDict

from .models import CaseSnapshot, Evidence, RecordRole, SourceType, TrustTier


MAX_SAMPLE_GAP_SECONDS = 90.0
DUPLICATE_TOLERANCE_METERS = 5.0
EARTH_RADIUS_METERS = 6_371_000.0


class GpsAggregationResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    coverage_percent: float
    actual_distance_m: float
    unique_sample_count: int
    conflict: bool
    conflict_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Sample:
    timestamp: datetime
    latitude: float
    longitude: float
    evidence_id: str
    record_role: RecordRole


ROLE_PRIORITY = {
    RecordRole.CORRECTION: 0,
    RecordRole.SUPPLEMENT: 1,
    RecordRole.ORIGINAL: 2,
}


def haversine_m(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (a_lat, a_lon, b_lat, b_lon))
    d_lat = lat2 - lat1
    d_lon = lon2 - lon1
    term = sin(d_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(d_lon / 2) ** 2
    return 2 * EARTH_RADIUS_METERS * asin(sqrt(term))


def _merge_intervals(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    ordered = sorted(intervals, key=lambda interval: interval[0])
    if not ordered:
        return 0.0
    merged: list[tuple[datetime, datetime]] = []
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            merged.append((current_start, current_end))
            current_start, current_end = start, end
    merged.append((current_start, current_end))
    return sum((end - start).total_seconds() for start, end in merged)


def aggregate_gps(snapshot: CaseSnapshot, evidence_by_id: dict[str, Evidence]) -> GpsAggregationResult:
    samples: list[_Sample] = []
    complete_reported_distances: list[tuple[int, str, float]] = []
    reasons: list[str] = []

    for evidence_id in snapshot.evidence_refs:
        evidence = evidence_by_id.get(evidence_id)
        if evidence is None or evidence.source_type != SourceType.PLATFORM_GPS:
            continue
        if evidence.origin_case_id != snapshot.case_id:
            reasons.append(f"{evidence_id}: origin_case_id mismatch")
            continue
        if evidence.trust_tier != TrustTier.AUTHORITATIVE:
            reasons.append(f"{evidence_id}: GPS must be authoritative")
            continue

        reported_distance = evidence.payload.get("reported_actual_distance_m")
        coverage = evidence.coverage
        if (
            reported_distance is not None
            and coverage is not None
            and coverage.is_complete
            and coverage.start_at <= snapshot.trip_started_at
            and coverage.end_at >= snapshot.trip_ended_at
        ):
            try:
                parsed_distance = float(reported_distance)
            except (TypeError, ValueError):
                reasons.append(f"{evidence_id}: invalid reported_actual_distance_m")
            else:
                if parsed_distance < 0:
                    reasons.append(f"{evidence_id}: reported distance must be non-negative")
                else:
                    complete_reported_distances.append(
                        (ROLE_PRIORITY[evidence.record_role], evidence_id, parsed_distance)
                    )

        for raw in evidence.payload.get("samples", []):
            timestamp = datetime.fromisoformat(raw["timestamp"])
            latitude = float(raw["latitude"])
            longitude = float(raw["longitude"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                reasons.append(f"{evidence_id}: invalid coordinate")
                continue
            # A sample exactly at trip end is accepted as a coverage boundary.
            if snapshot.trip_started_at <= timestamp <= snapshot.trip_ended_at:
                samples.append(
                    _Sample(
                        timestamp=timestamp,
                        latitude=latitude,
                        longitude=longitude,
                        evidence_id=evidence_id,
                        record_role=evidence.record_role,
                    )
                )

    grouped: dict[datetime, list[_Sample]] = {}
    for sample in samples:
        grouped.setdefault(sample.timestamp, []).append(sample)

    unique: list[_Sample] = []
    for timestamp in sorted(grouped):
        candidates = sorted(
            grouped[timestamp],
            key=lambda sample: (ROLE_PRIORITY[sample.record_role], sample.evidence_id),
        )
        chosen = candidates[0]
        for candidate in candidates[1:]:
            if haversine_m(
                chosen.latitude,
                chosen.longitude,
                candidate.latitude,
                candidate.longitude,
            ) > DUPLICATE_TOLERANCE_METERS:
                reasons.append(f"conflicting authoritative GPS at {timestamp.isoformat()}")
        unique.append(chosen)

    intervals: list[tuple[datetime, datetime]] = []
    actual_distance_m = 0.0
    for left, right in zip(unique, unique[1:]):
        gap_seconds = (right.timestamp - left.timestamp).total_seconds()
        if 0 < gap_seconds <= MAX_SAMPLE_GAP_SECONDS:
            intervals.append((left.timestamp, right.timestamp))
            actual_distance_m += haversine_m(
                left.latitude,
                left.longitude,
                right.latitude,
                right.longitude,
            )

    trip_seconds = (snapshot.trip_ended_at - snapshot.trip_started_at).total_seconds()
    covered_seconds = _merge_intervals(intervals)
    coverage_percent = 100.0 * covered_seconds / trip_seconds

    # Some authoritative platform exports provide a verified trip-level distance
    # together with representative (rather than high-frequency) GPS samples. In
    # that contract the complete coverage window and reported distance are the
    # canonical business facts; the samples remain useful for provenance and
    # coordinate validation but must not be reinterpreted as missing telemetry.
    if complete_reported_distances:
        complete_reported_distances.sort(key=lambda item: (item[0], item[1]))
        selected_priority, selected_evidence_id, selected_distance = complete_reported_distances[0]
        for priority, evidence_id, distance in complete_reported_distances[1:]:
            if priority != selected_priority:
                continue
            if abs(distance - selected_distance) > DUPLICATE_TOLERANCE_METERS:
                reasons.append(
                    "conflicting authoritative reported GPS distances: "
                    f"{selected_evidence_id} vs {evidence_id}"
                )
        coverage_percent = 100.0
        actual_distance_m = selected_distance

    return GpsAggregationResult(
        coverage_percent=coverage_percent,
        actual_distance_m=actual_distance_m,
        unique_sample_count=len(unique),
        conflict=bool(reasons),
        conflict_reasons=tuple(reasons),
    )
