from __future__ import annotations

from .integrity import EvidenceIntegrityError, compute_input_fingerprint, index_evidence
from .models import (
    CaseSnapshot,
    DecisionDelta,
    Evidence,
    JudgeRecommendation,
    PolicyEvaluation,
    RecordRole,
    SourceType,
    TrustTier,
)
from .policy import PolicyFile, OutputIntegrityError, validate_judge_recommendation, validate_policy_contract


NON_BUSINESS_FIELDS = {"case_version", "created_at", "evidence_refs"}


def _normalized_case(snapshot: CaseSnapshot) -> dict:
    value = snapshot.model_dump(mode="json")
    for field in NON_BUSINESS_FIELDS:
        value.pop(field, None)
    return value


def _judge_is_consistent(
    evaluation: PolicyEvaluation,
    recommendation: JudgeRecommendation | None,
) -> bool:
    if recommendation is None:
        return False
    try:
        validate_judge_recommendation(evaluation, recommendation)
    except OutputIntegrityError:
        return False
    return True


def build_decision_delta(
    before_case: CaseSnapshot,
    after_case: CaseSnapshot,
    before_evaluation: PolicyEvaluation,
    after_evaluation: PolicyEvaluation,
    before_judge: JudgeRecommendation | None,
    after_judge: JudgeRecommendation | None,
    *,
    evidence: list[Evidence],
    policy: PolicyFile,
) -> DecisionDelta:
    reasons: list[str] = []
    if before_case.case_id != after_case.case_id:
        reasons.append("case_id differs")
    if before_case.policy_version != after_case.policy_version:
        reasons.append("policy_version differs")
    if after_case.case_version <= before_case.case_version:
        reasons.append("to_version must be newer")
    if _normalized_case(before_case) != _normalized_case(after_case):
        reasons.append("business inputs other than evidence changed")

    before_refs = set(before_case.evidence_refs)
    after_refs = set(after_case.evidence_refs)
    added = sorted(after_refs - before_refs)
    removed = sorted(before_refs - after_refs)
    if len(added) != 1 or removed:
        reasons.append("comparison requires exactly one added evidence reference and no removals")

    try:
        validate_policy_contract(policy)
        evidence_by_id = index_evidence(evidence)
        before_fingerprint = compute_input_fingerprint(before_case, evidence_by_id, policy)
        after_fingerprint = compute_input_fingerprint(after_case, evidence_by_id, policy)
    except (EvidenceIntegrityError, ValueError) as exc:
        reasons.append(f"evidence or policy integrity failed: {exc}")
        evidence_by_id = {}
        before_fingerprint = None
        after_fingerprint = None

    if before_fingerprint is not None and before_evaluation.input_fingerprint != before_fingerprint:
        reasons.append("before evaluation is not bound to the compared snapshot, evidence, and policy")
    if after_fingerprint is not None and after_evaluation.input_fingerprint != after_fingerprint:
        reasons.append("after evaluation is not bound to the compared snapshot, evidence, and policy")

    if len(added) == 1 and added[0] in evidence_by_id:
        changed_evidence = evidence_by_id[added[0]]
        if changed_evidence.source_type != SourceType.PLATFORM_GPS:
            reasons.append("added evidence must be PLATFORM_GPS")
        if changed_evidence.trust_tier != TrustTier.AUTHORITATIVE:
            reasons.append("added GPS evidence must be authoritative")
        if changed_evidence.record_role != RecordRole.SUPPLEMENT:
            reasons.append("added GPS evidence must be marked as a supplement")
        if not changed_evidence.related_evidence_ids or not set(changed_evidence.related_evidence_ids).issubset(before_refs):
            reasons.append("added GPS supplement must identify its prior evidence lineage")

    changed_facts = sorted(
        fact_id
        for fact_id in set(before_evaluation.facts) | set(after_evaluation.facts)
        if before_evaluation.facts.get(fact_id) != after_evaluation.facts.get(fact_id)
    )
    changed_rules = tuple(
        sorted(set(before_evaluation.matched_rule_ids) ^ set(after_evaluation.matched_rule_ids))
    )
    before_judge_consistent = _judge_is_consistent(before_evaluation, before_judge)
    after_judge_consistent = _judge_is_consistent(after_evaluation, after_judge)

    before_amount = before_evaluation.allowed_action.amount_cents if before_evaluation.allowed_action else 0
    after_amount = after_evaluation.allowed_action.amount_cents if after_evaluation.allowed_action else 0
    action_or_status_changed = (
        before_evaluation.business_status != after_evaluation.business_status
        or before_evaluation.allowed_action != after_evaluation.allowed_action
    )
    comparable = not reasons
    causal_claim_allowed = (
        comparable
        and len(changed_facts) == 1
        and bool(changed_rules)
        and action_or_status_changed
        and before_judge_consistent
        and after_judge_consistent
    )

    if causal_claim_allowed:
        message = (
            "Under DEMO_POLICY_V1 with all other business inputs fixed, supplemental GPS "
            "evidence changed the program-evaluated fact, rule outcome, and simulated ruling."
        )
    elif not comparable:
        message = "Decision Delta is unavailable: " + "; ".join(reasons)
    elif not before_judge_consistent or not after_judge_consistent:
        message = "Program rule output changed, but the Judge recommendation failed consistency validation."
    else:
        message = "Evidence or argument changed, but the deterministic simulated ruling did not change."

    return DecisionDelta(
        case_id=before_case.case_id,
        from_version=before_case.case_version,
        to_version=after_case.case_version,
        policy_version=before_case.policy_version,
        comparable=comparable,
        not_comparable_reasons=tuple(reasons),
        changed_evidence_id=added[0] if len(added) == 1 else None,
        changed_fact_id=changed_facts[0] if len(changed_facts) == 1 else None,
        changed_rule_ids=changed_rules,
        business_status_before=before_evaluation.business_status,
        business_status_after=after_evaluation.business_status,
        action_before=before_evaluation.allowed_action,
        action_after=after_evaluation.allowed_action,
        refund_delta_cents=after_amount - before_amount,
        judge_consistent_before=before_judge_consistent,
        judge_consistent_after=after_judge_consistent,
        causal_claim_allowed=causal_claim_allowed,
        display_message=message,
    )
