from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .case_store import CaseStore
from .models import CaseSnapshot
from .run_registry import RunRegistry
from .session_auth import RunContextSigner


class IntakeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_query: str = Field(min_length=1, max_length=4000)
    case_reference: str | None = Field(default=None, min_length=1, max_length=128)
    trip_reference: str | None = Field(default=None, min_length=1, max_length=128)


class ResolutionStatus(StrEnum):
    MATCHED = "MATCHED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True)
class Resolution:
    status: ResolutionStatus
    snapshot: CaseSnapshot | None
    reference_kind: str | None
    message: str


_CASE_REFERENCE = re.compile(r"(?<![A-Z0-9])DISP[\s_-]*0*([1-9][0-9]*)(?![A-Z0-9])", re.I)
_TRIP_REFERENCE = re.compile(r"(?<![A-Z0-9])TRIP[\s_-]*(\d{4})[\s_-]*(\d{4,})(?![A-Z0-9])", re.I)


def _canonical_case_reference(value: str) -> str | None:
    match = _CASE_REFERENCE.fullmatch(value.strip())
    if not match:
        return None
    return f"DISP-{int(match.group(1)):03d}"


def _canonical_trip_reference(value: str) -> str | None:
    match = _TRIP_REFERENCE.fullmatch(value.strip())
    if not match:
        return None
    return f"TRIP-{match.group(1)}-{match.group(2)}"


class OfficialCaseResolver:
    """Resolve only explicit identifiers against the official case set.

    Natural-language similarity is deliberately not used to select a case. A
    description without an exact official case or trip reference must request
    clarification rather than silently binding the wrong person's record.
    """

    def __init__(self, store: CaseStore) -> None:
        snapshots = store.list_official_snapshots()
        self._by_case_id = {snapshot.case_id.upper(): snapshot for snapshot in snapshots}
        self._by_trip_reference: dict[str, CaseSnapshot] = {}
        for snapshot in snapshots:
            for evidence in store.get_evidence(snapshot):
                source_prefix = evidence.source_record_id.split(":", 1)[0].upper()
                canonical = _canonical_trip_reference(source_prefix)
                if canonical:
                    existing = self._by_trip_reference.get(canonical)
                    if existing is not None and existing.case_id != snapshot.case_id:
                        raise ValueError(f"trip reference maps to multiple official cases: {canonical}")
                    self._by_trip_reference[canonical] = snapshot

    def resolve(self, request: IntakeRequest) -> Resolution:
        supplied: list[tuple[str, str]] = []
        invalid_explicit = False

        if request.case_reference:
            canonical = _canonical_case_reference(request.case_reference)
            if canonical:
                supplied.append(("CASE_REFERENCE", canonical))
            else:
                invalid_explicit = True
        if request.trip_reference:
            canonical = _canonical_trip_reference(request.trip_reference)
            if canonical:
                supplied.append(("TRIP_REFERENCE", canonical))
            else:
                invalid_explicit = True

        for match in _CASE_REFERENCE.finditer(request.user_query):
            supplied.append(("CASE_REFERENCE", f"DISP-{int(match.group(1)):03d}"))
        for match in _TRIP_REFERENCE.finditer(request.user_query):
            supplied.append(
                ("TRIP_REFERENCE", f"TRIP-{match.group(1)}-{match.group(2)}")
            )

        if invalid_explicit:
            return Resolution(
                status=ResolutionStatus.NOT_FOUND,
                snapshot=None,
                reference_kind=None,
                message="The supplied case or trip reference format is invalid.",
            )

        if not supplied:
            return Resolution(
                status=ResolutionStatus.NEEDS_CLARIFICATION,
                snapshot=None,
                reference_kind=None,
                message=(
                    "Please provide the official case reference (for example DISP-001) "
                    "or trip reference (for example TRIP-2026-09871)."
                ),
            )

        matches: dict[str, tuple[CaseSnapshot, str]] = {}
        unknown = False
        for kind, reference in supplied:
            snapshot = (
                self._by_case_id.get(reference)
                if kind == "CASE_REFERENCE"
                else self._by_trip_reference.get(reference)
            )
            if snapshot is None:
                unknown = True
                continue
            matches[snapshot.case_id] = (snapshot, kind)

        if unknown and not matches:
            return Resolution(
                status=ResolutionStatus.NOT_FOUND,
                snapshot=None,
                reference_kind=None,
                message="No official case matched the supplied reference.",
            )
        if unknown or len(matches) != 1:
            return Resolution(
                status=ResolutionStatus.NEEDS_CLARIFICATION,
                snapshot=None,
                reference_kind=None,
                message="The supplied references conflict or are ambiguous; please provide one official reference.",
            )
        snapshot, kind = next(iter(matches.values()))
        return Resolution(
            status=ResolutionStatus.MATCHED,
            snapshot=snapshot,
            reference_kind=kind,
            message="The official case was matched and a protected workflow session was created.",
        )


class IntakeService:
    def __init__(
        self,
        resolver: OfficialCaseResolver,
        registry: RunRegistry,
        signer: RunContextSigner,
        *,
        run_ttl_seconds: int = 3600,
        max_requests_per_role: int = 300,
    ) -> None:
        self.resolver = resolver
        self.registry = registry
        self.signer = signer
        self.run_ttl_seconds = run_ttl_seconds
        self.max_requests_per_role = max_requests_per_role

    def resolve_case_context(self, request: IntakeRequest) -> dict:
        resolution = self.resolver.resolve(request)
        if resolution.snapshot is None:
            return {
                "resolution_status": resolution.status.value,
                "message": resolution.message,
                "run_created": False,
            }
        snapshot = resolution.snapshot
        issued = self.registry.create_run(
            snapshot.case_id,
            snapshot.case_version,
            ttl_seconds=self.run_ttl_seconds,
            max_requests_per_role=self.max_requests_per_role,
        )
        return {
            "resolution_status": resolution.status.value,
            "message": resolution.message,
            "run_created": True,
            "run_id": issued.run_id,
            "run_context": self.signer.issue(issued),
            "case_id": issued.case_id,
            "case_version": issued.case_version,
            "policy_version": issued.policy_version,
            "expires_at": issued.expires_at.isoformat(),
            "reference_kind": resolution.reference_kind,
            "data_precedence": "OFFICIAL_OVER_LEGACY_MOCK",
        }
