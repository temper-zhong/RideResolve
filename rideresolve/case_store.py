from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .integrity import EvidenceIntegrityError, evidence_checksum_is_valid, index_evidence
from .models import CaseSnapshot, Evidence, SourceType
from .policy import PolicyFile, load_policy


class CaseNotFoundError(LookupError):
    pass


class PolicyNotFoundError(LookupError):
    pass


class CaseStore:
    def __init__(
        self,
        cases: list[CaseSnapshot],
        evidence: list[Evidence],
        policies: dict[str, PolicyFile],
        *,
        dataset_id: str,
        synthetic: bool,
        official_case_keys: set[tuple[str, int]] | None = None,
    ) -> None:
        self.dataset_id = dataset_id
        self.synthetic = synthetic
        self._cases: dict[tuple[str, int], CaseSnapshot] = {}
        for snapshot in cases:
            key = (snapshot.case_id, snapshot.case_version)
            if key in self._cases:
                raise ValueError(f"duplicate case snapshot: {key}")
            self._cases[key] = snapshot
        self._evidence = index_evidence(evidence)
        self._policies = policies
        self._official_case_keys = frozenset(official_case_keys or ())
        self._validate()

    @classmethod
    def load_default(cls) -> "CaseStore":
        root = Path(__file__).resolve().parents[1]
        data_paths = (
            root / "data" / "cases" / "tool_cases.json",
            root / "data" / "cases" / "official_cases.json",
        )
        policy_paths = (
            root / "data" / "policies" / "DEMO_POLICY_V1.json",
            root / "data" / "policies" / "RYDE_POLICY_V2_1.json",
        )
        datasets: list[dict[str, Any]] = [
            json.loads(path.read_text(encoding="utf-8"))
            for path in data_paths
            if path.exists()
        ]
        cases = [
            CaseSnapshot.model_validate(item)
            for dataset in datasets
            for item in dataset["cases"]
        ]
        evidence = [
            Evidence.model_validate(item)
            for dataset in datasets
            for item in dataset["evidence"]
        ]
        policies = [load_policy(path) for path in policy_paths if path.exists()]
        official_case_keys = {
            (str(item["case_id"]), int(item["case_version"]))
            for dataset in datasets
            if dataset.get("source_kind") == "OFFICIAL_HACKATHON_SAMPLE_DATASET"
            for item in dataset["cases"]
        }
        return cls(
            cases,
            evidence,
            {policy.policy_version: policy for policy in policies},
            dataset_id="RIDERESOLVE_MERGED_MOCK_AND_OFFICIAL_SAMPLES_V1",
            synthetic=all(bool(dataset["synthetic"]) for dataset in datasets),
            official_case_keys=official_case_keys,
        )

    def _validate(self) -> None:
        for snapshot in self._cases.values():
            if snapshot.policy_version not in self._policies:
                raise PolicyNotFoundError(snapshot.policy_version)
            for evidence_id in snapshot.evidence_refs:
                item = self._evidence.get(evidence_id)
                if item is None:
                    raise EvidenceIntegrityError(f"missing evidence entity: {evidence_id}")
                if item.origin_case_id != snapshot.case_id:
                    raise EvidenceIntegrityError(f"cross-case evidence reference: {evidence_id}")
                if not evidence_checksum_is_valid(item):
                    raise EvidenceIntegrityError(f"checksum mismatch: {evidence_id}")

    def get_snapshot(self, case_id: str, case_version: int) -> CaseSnapshot:
        try:
            return self._cases[(case_id, case_version)]
        except KeyError as exc:
            raise CaseNotFoundError(f"case snapshot not found: {case_id} v{case_version}") from exc

    def get_evidence(
        self,
        snapshot: CaseSnapshot,
        source_types: set[SourceType] | None = None,
    ) -> list[Evidence]:
        result = [self._evidence[evidence_id] for evidence_id in snapshot.evidence_refs]
        if source_types is not None:
            result = [item for item in result if item.source_type in source_types]
        return result

    def get_policy(self, policy_version: str) -> PolicyFile:
        try:
            return self._policies[policy_version]
        except KeyError as exc:
            raise PolicyNotFoundError(f"policy not found: {policy_version}") from exc

    def list_official_snapshots(self) -> tuple[CaseSnapshot, ...]:
        """Return only snapshots supplied by the official dataset, in stable order."""
        return tuple(
            self._cases[key]
            for key in sorted(self._official_case_keys)
        )
