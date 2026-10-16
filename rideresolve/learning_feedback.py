from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import Action, BusinessStatus, DisputeType

if TYPE_CHECKING:
    from .demo_service import EvaluatedDemoCase


class FeedbackIntegrityError(ValueError):
    """A feedback record cannot be trusted or published."""


class ReviewerCorrection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    feedback_id: str
    source_case_id: str
    source_case_version: int = Field(ge=1)
    dispute_type: DisputeType
    policy_version: str
    reviewed_at: datetime
    reviewer_role: Literal["HUMAN_REVIEWER"] = "HUMAN_REVIEWER"
    original_status: BusinessStatus
    original_action: Action | None
    corrected_status: BusinessStatus
    corrected_action: Action | None
    source_rule_ids: tuple[str, ...]
    evidence_citations: tuple[str, ...]
    correction_reason: str = Field(min_length=20)
    synthetic: Literal[True] = True
    publication_status: Literal["APPROVED_FOR_PRECEDENT"]
    learning_scope: Literal["ADVISORY_PRECEDENT_ONLY"]
    checksum: str = ""

    @model_validator(mode="after")
    def validate_correction(self) -> "ReviewerCorrection":
        for label, status, action in (
            ("original", self.original_status, self.original_action),
            ("corrected", self.corrected_status, self.corrected_action),
        ):
            if status == BusinessStatus.RESOLVED and action is None:
                raise ValueError(f"{label} RESOLVED outcome requires an action")
            if status == BusinessStatus.PENDING_HUMAN_REVIEW and action is not None:
                raise ValueError(f"{label} pending-review outcome requires action=null")
        if (
            self.original_status == self.corrected_status
            and self.original_action == self.corrected_action
        ):
            raise ValueError("feedback must describe a genuine human override")
        if not self.source_rule_ids:
            raise ValueError("feedback must cite at least one source rule")
        if not self.evidence_citations:
            raise ValueError("feedback must cite the reviewed evidence package")
        if len(set(self.source_rule_ids)) != len(self.source_rule_ids):
            raise ValueError("source_rule_ids must be unique")
        if len(set(self.evidence_citations)) != len(self.evidence_citations):
            raise ValueError("evidence_citations must be unique")
        return self


def _canonical_feedback_bytes(record: ReviewerCorrection) -> bytes:
    payload = record.model_dump(mode="json", exclude={"checksum"})
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def compute_feedback_checksum(record: ReviewerCorrection) -> str:
    return "sha256:" + hashlib.sha256(_canonical_feedback_bytes(record)).hexdigest()


def feedback_checksum_is_valid(record: ReviewerCorrection) -> bool:
    return record.checksum == compute_feedback_checksum(record)


def capture_reviewer_correction(**fields: object) -> ReviewerCorrection:
    """Validate and fingerprint one approved human override."""
    draft = ReviewerCorrection.model_validate({**fields, "checksum": ""})
    return draft.model_copy(update={"checksum": compute_feedback_checksum(draft)})


@dataclass(frozen=True)
class PrecedentKnowledgeBase:
    knowledge_base_id: str
    synthetic: bool
    records: tuple[ReviewerCorrection, ...]

    @classmethod
    def load_default(cls) -> "PrecedentKnowledgeBase":
        root = Path(__file__).resolve().parents[1]
        path = root / "data" / "feedback" / "approved_precedents.json"
        return cls.load(path)

    @classmethod
    def load(cls, path: Path) -> "PrecedentKnowledgeBase":
        raw = json.loads(path.read_text(encoding="utf-8"))
        records = tuple(ReviewerCorrection.model_validate(item) for item in raw["records"])
        knowledge_base = cls(
            knowledge_base_id=str(raw["knowledge_base_id"]),
            synthetic=bool(raw["synthetic"]),
            records=records,
        )
        knowledge_base.validate()
        return knowledge_base

    @classmethod
    def empty(
        cls,
        knowledge_base_id: str = "RIDERESOLVE_PRECEDENT_MEMORY_V1",
        *,
        synthetic: bool = True,
    ) -> "PrecedentKnowledgeBase":
        return cls(knowledge_base_id=knowledge_base_id, synthetic=synthetic, records=())

    def validate(self) -> None:
        seen: set[str] = set()
        for record in self.records:
            if record.feedback_id in seen:
                raise FeedbackIntegrityError(f"duplicate feedback ID: {record.feedback_id}")
            seen.add(record.feedback_id)
            if not feedback_checksum_is_valid(record):
                raise FeedbackIntegrityError(f"feedback checksum mismatch: {record.feedback_id}")

    def publish(self, record: ReviewerCorrection) -> "PrecedentKnowledgeBase":
        if not feedback_checksum_is_valid(record):
            raise FeedbackIntegrityError(f"feedback checksum mismatch: {record.feedback_id}")
        if any(item.feedback_id == record.feedback_id for item in self.records):
            raise FeedbackIntegrityError(f"duplicate feedback ID: {record.feedback_id}")
        updated = PrecedentKnowledgeBase(
            knowledge_base_id=self.knowledge_base_id,
            synthetic=self.synthetic,
            records=(*self.records, record),
        )
        updated.validate()
        return updated

    def save(self, path: Path) -> None:
        """Atomically persist the validated append-only knowledge-base state."""
        self.validate()
        if path.exists():
            existing = PrecedentKnowledgeBase.load(path)
            if (
                existing.knowledge_base_id != self.knowledge_base_id
                or existing.synthetic != self.synthetic
            ):
                raise FeedbackIntegrityError("knowledge-base identity cannot change")
            current_by_id = {record.feedback_id: record for record in self.records}
            for record in existing.records:
                if current_by_id.get(record.feedback_id) != record:
                    raise FeedbackIntegrityError(
                        f"append-only knowledge base cannot remove or rewrite: {record.feedback_id}"
                    )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        payload = {
            "knowledge_base_id": self.knowledge_base_id,
            "synthetic": self.synthetic,
            "records": [record.model_dump(mode="json") for record in self.records],
        }
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)


@dataclass(frozen=True)
class PrecedentMatch:
    feedback_id: str
    similarity_score: int
    source_case_id: str
    source_rule_ids: tuple[str, ...]
    corrected_status: BusinessStatus
    corrected_action: Action | None
    correction_reason: str


@dataclass(frozen=True)
class PolicyPrecedentReport:
    agent_name: Literal["Policy & Precedent Agent"]
    execution_mode: Literal["SYNTHETIC_OFFLINE"]
    knowledge_base_id: str
    query_dispute_type: DisputeType
    query_policy_version: str
    query_rule_ids: tuple[str, ...]
    matches: tuple[PrecedentMatch, ...]
    advisory: str
    judge_context: dict[str, object]
    may_change_policy_or_outcome: Literal[False] = False


def retrieve_approved_precedents(
    *,
    dispute_type: DisputeType,
    policy_version: str,
    rule_ids: tuple[str, ...],
    knowledge_base: PrecedentKnowledgeBase,
    limit: int = 3,
) -> tuple[tuple[PrecedentMatch, ...], str]:
    """Return integrity-checked advisory matches for server-derived policy context."""
    if limit < 1 or limit > 3:
        raise ValueError("limit must be between 1 and 3")
    knowledge_base.validate()
    query_rules = set(rule_ids)
    ranked: list[PrecedentMatch] = []

    for record in knowledge_base.records:
        if record.dispute_type != dispute_type:
            continue
        overlapping_rules = query_rules & set(record.source_rule_ids)
        if not overlapping_rules:
            continue
        score = 60 + min(20, 10 * len(overlapping_rules))
        if record.policy_version == policy_version:
            score += 20
        ranked.append(
            PrecedentMatch(
                feedback_id=record.feedback_id,
                similarity_score=min(100, score),
                source_case_id=record.source_case_id,
                source_rule_ids=record.source_rule_ids,
                corrected_status=record.corrected_status,
                corrected_action=record.corrected_action,
                correction_reason=record.correction_reason,
            )
        )

    ranked.sort(key=lambda item: (-item.similarity_score, item.feedback_id))
    matches = tuple(ranked[:limit])
    if matches:
        advisory = (
            "Reviewer-approved precedents exist for the matched rule. Check whether the cited "
            "late or corrected evidence condition is present; do not copy the historical outcome."
        )
    else:
        advisory = (
            "No reviewer-approved precedent matched the current dispute type and rule. "
            "Apply the current versioned policy without inventing precedent."
        )
    return matches, advisory


def run_policy_precedent_agent(
    case: EvaluatedDemoCase,
    knowledge_base: PrecedentKnowledgeBase | None = None,
    *,
    limit: int = 3,
) -> PolicyPrecedentReport:
    """Retrieve reviewer-approved precedents without changing current policy output."""
    if limit < 1:
        raise ValueError("limit must be positive")
    knowledge_base = knowledge_base or PrecedentKnowledgeBase.load_default()
    matches, advisory = retrieve_approved_precedents(
        dispute_type=case.snapshot.dispute_type,
        policy_version=case.snapshot.policy_version,
        rule_ids=tuple(case.evaluation.matched_rule_ids),
        knowledge_base=knowledge_base,
        limit=limit,
    )

    judge_context: dict[str, object] = {
        "precedent_ids": [item.feedback_id for item in matches],
        "advisory": advisory,
        "authority": "ADVISORY_ONLY",
        "may_override_policy": False,
    }
    return PolicyPrecedentReport(
        agent_name="Policy & Precedent Agent",
        execution_mode="SYNTHETIC_OFFLINE",
        knowledge_base_id=knowledge_base.knowledge_base_id,
        query_dispute_type=case.snapshot.dispute_type,
        query_policy_version=case.snapshot.policy_version,
        query_rule_ids=tuple(case.evaluation.matched_rule_ids),
        matches=matches,
        advisory=advisory,
        judge_context=judge_context,
    )


def feedback_loop_steps(
    knowledge_base: PrecedentKnowledgeBase,
    report: PolicyPrecedentReport,
) -> tuple[dict[str, str], ...]:
    """Return an observable, non-mutating audit view of the persisted loop."""
    return (
        {
            "Stage": "Human override captured",
            "Control": "Outcome changed, reason and evidence citations required",
            "Result": f"{len(knowledge_base.records)} approved synthetic record(s)",
        },
        {
            "Stage": "Integrity and publication check",
            "Control": "Checksum + unique feedback ID + advisory-only scope",
            "Result": "PASS",
        },
        {
            "Stage": "Precedent retrieval",
            "Control": "Same dispute type + overlapping rule + policy version ranking",
            "Result": f"{len(report.matches)} match(es) supplied to Judge context",
        },
        {
            "Stage": "Policy boundary",
            "Control": "Precedent cannot change policy, status, action, or money",
            "Result": "ENFORCED",
        },
    )
