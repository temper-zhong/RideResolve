from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any

from pydantic import BaseModel

from .models import CaseSnapshot, Evidence


class EvidenceIntegrityError(ValueError):
    """A snapshot references missing, cross-case, or tampered evidence."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_evidence_checksum(evidence: Evidence) -> str:
    content = evidence.model_dump(mode="json", exclude={"checksum"})
    digest = hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def evidence_checksum_is_valid(evidence: Evidence) -> bool:
    return evidence.checksum == compute_evidence_checksum(evidence)


def index_evidence(evidence: Iterable[Evidence]) -> dict[str, Evidence]:
    """Build an evidence index without silently accepting duplicate identities."""
    result: dict[str, Evidence] = {}
    for item in evidence:
        if item.evidence_id in result:
            raise EvidenceIntegrityError(f"duplicate evidence entity: {item.evidence_id}")
        result[item.evidence_id] = item
    return result


def compute_input_fingerprint(
    snapshot: CaseSnapshot,
    evidence_by_id: dict[str, Evidence],
    policy: BaseModel,
) -> str:
    referenced: list[dict[str, Any]] = []
    for evidence_id in sorted(snapshot.evidence_refs):
        item = evidence_by_id.get(evidence_id)
        if item is None:
            raise EvidenceIntegrityError(f"missing evidence entity: {evidence_id}")
        if item.origin_case_id != snapshot.case_id:
            raise EvidenceIntegrityError(f"cross-case evidence reference: {evidence_id}")
        if not evidence_checksum_is_valid(item):
            raise EvidenceIntegrityError(f"checksum mismatch: {evidence_id}")
        referenced.append(item.model_dump(mode="json"))

    content = {
        "snapshot": snapshot.model_dump(mode="json"),
        "evidence": referenced,
        "policy": policy.model_dump(mode="json"),
    }
    return "sha256:" + hashlib.sha256(_canonical_json(content).encode("utf-8")).hexdigest()
