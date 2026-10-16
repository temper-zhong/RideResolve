from __future__ import annotations

from typing import Any

import streamlit as st

from rideresolve.case_store import CaseStore
from rideresolve.demo_service import (
    DeltaDemo,
    EvaluatedDemoCase,
    advocate_panels,
    evaluate_demo_case,
    gate_rows,
    historical_context_rows,
    load_delta_demo,
    program_evidence_sufficiency,
    chat_semantic_signals,
)
from rideresolve.models import Action, BusinessStatus, FactStatus
from rideresolve.learning_feedback import (
    PolicyPrecedentReport,
    PrecedentKnowledgeBase,
    feedback_loop_steps,
    run_policy_precedent_agent,
)
from rideresolve.stretch_goals import (
    EscalationPacket,
    EvidenceCollectionReport,
    build_escalation_packet,
    run_evidence_collection_agent,
)


st.set_page_config(
    page_title="RideResolve",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
    .block-container {max-width: 1240px; padding-top: 1.5rem; padding-bottom: 4rem;}
    .rr-kicker {font-size: .78rem; letter-spacing: .13em; text-transform: uppercase; color: #5b6b83; font-weight: 700;}
    .rr-title {font-size: 2.55rem; line-height: 1.05; font-weight: 760; color: #14213d; margin: .25rem 0 .55rem;}
    .rr-subtitle {font-size: 1.05rem; color: #526078; max-width: 820px; margin-bottom: 1rem;}
    .rr-pill {display: inline-block; padding: .3rem .7rem; border-radius: 999px; background: #fff1cf; color: #7b5300; font-weight: 750; font-size: .76rem; letter-spacing: .08em;}
    .rr-card {border: 1px solid #dce3ed; border-radius: 14px; padding: 1rem 1.05rem; background: #ffffff; min-height: 112px;}
    .rr-card-label {font-size: .75rem; color: #68768c; text-transform: uppercase; letter-spacing: .08em; font-weight: 700;}
    .rr-card-value {font-size: 1.15rem; color: #15243b; font-weight: 730; margin-top: .35rem;}
    .rr-note {border-left: 4px solid #5271ff; padding: .75rem 1rem; background: #f5f7ff; border-radius: 8px; color: #33425c;}
    .rr-section {margin-top: 1.2rem;}
    div[data-testid="stMetric"] {border: 1px solid #e0e6ef; padding: .85rem; border-radius: 12px; background: #fbfcfe;}
    div[data-testid="stMetricValue"] {font-size: 1.3rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_store() -> CaseStore:
    return CaseStore.load_default()


@st.cache_resource
def load_delta() -> DeltaDemo:
    return load_delta_demo(load_store())


@st.cache_resource
def load_precedent_memory() -> PrecedentKnowledgeBase:
    return PrecedentKnowledgeBase.load_default()


def action_text(action: Action | None) -> str:
    if action is None:
        return "No automated action"
    if action.amount_cents == 0:
        return action.type.value
    return f"{action.type.value} · {action.currency} {action.amount_cents / 100:.2f} · {action.fee_item}"


def final_status_text(case: EvaluatedDemoCase, escalation: EscalationPacket) -> str:
    if escalation.effective_status == BusinessStatus.RESOLVED:
        return "Simulated resolution complete"
    return "Pending human review"


def render_case_header(case: EvaluatedDemoCase) -> None:
    st.markdown("### 1 · Case selection and current version")
    left, middle, right, last = st.columns(4)
    left.metric("Case", case.snapshot.case_id)
    middle.metric("Version", f"v{case.snapshot.case_version}")
    right.metric("Dispute", case.snapshot.dispute_type.value.replace("_", " ").title())
    last.metric("Policy", case.snapshot.policy_version)
    st.caption(case.snapshot.claim_text)


def render_evidence(case: EvaluatedDemoCase) -> None:
    st.markdown("### 2 · Evidence summary and provenance")
    rows = [
        {
            "Evidence ID": item.evidence_id,
            "Source": item.source_type.value,
            "Trust": item.trust_tier.value,
            "Role": item.record_role.value,
            "Coverage": "complete" if item.coverage and item.coverage.is_complete else "partial / n.a.",
        }
        for item in case.evidence
    ]
    st.table(rows)
    selected_id = st.selectbox(
        "Inspect one evidence record",
        [item.evidence_id for item in case.evidence],
        key=f"evidence-{case.snapshot.case_id}-{case.snapshot.case_version}",
    )
    item = next(record for record in case.evidence if record.evidence_id == selected_id)
    with st.expander(f"Provenance · {item.evidence_id}", expanded=False):
        st.write(item.provenance_reason)
        st.caption(f"Source record: {item.source_record_id} · checksum: {item.checksum[:24]}…")
        if item.related_evidence_ids:
            st.write("Related prior evidence:", ", ".join(item.related_evidence_ids))
        st.json(item.payload, expanded=False)


def render_evidence_collector(report: EvidenceCollectionReport) -> None:
    st.markdown("### Stretch 1 - Evidence Collection Agent")
    st.caption(
        "BONUS CAPABILITY - SYNTHETIC OFFLINE RUN. The collector autonomously chooses a bounded "
        "query plan from the dispute type and prepares one cited evidence package for both Advocates."
    )
    first, second, third = st.columns(3)
    first.metric("Records collected", len(report.collected_evidence_ids))
    second.metric("Source types", len(report.collected_source_types))
    third.metric("Package status", "READY" if report.ready_for_advocates else "NEEDS SUPPLEMENT")
    st.write(report.summary)
    rows = [
        {
            "Tool": step.operation,
            "Purpose": step.purpose,
            "Requested sources": ", ".join(step.requested_source_types) or "case / policy metadata",
            "Returned IDs": ", ".join(step.returned_evidence_ids) or "n.a.",
        }
        for step in report.steps
    ]
    st.table(rows)
    if report.gaps:
        st.warning("Collection gaps: " + " | ".join(report.gaps))
    else:
        st.success("The version-pinned evidence package is ready for the two Advocate agents.")
    st.caption(
        "Boundary: this Agent can retrieve and package evidence. It cannot determine liability, "
        "select a final outcome, or calculate a refund."
    )


def render_advocates(
    case: EvaluatedDemoCase,
    collector: EvidenceCollectionReport,
) -> None:
    st.markdown("### 3 · Independent advocate queries and arguments")
    rider, driver = advocate_panels(case, collector.collected_evidence_ids)
    for column, panel in zip(st.columns(2), (rider, driver)):
        with column:
            with st.container(border=True):
                st.markdown(f"#### {panel['role']}")
                st.caption("SYNTHETIC OFFLINE FIXTURE · not a live model run")
                st.write(panel["argument"])
                st.markdown("**Bounded query plan**")
                for query in panel["queries"]:
                    st.code(query, language=None)
                st.markdown("**Evidence citations**")
                st.write(" · ".join(panel["citations"]) or "None")

    signals = chat_semantic_signals(case)
    if signals:
        st.markdown("#### Conversation semantics")
        st.caption(
            "SYNTHETIC model-style annotations for sentiment, consent, disagreement, and threat. "
            "They help Advocates organize claims but never control policy, liability, status, or money."
        )
        st.table(signals)

    history = historical_context_rows(case)
    if history:
        st.markdown("#### Historical context")
        st.caption(
            "Supporting context only. Account age, dispute count, and rating patterns are excluded "
            "from the deterministic decision and cannot make either party more or less credible."
        )
        st.table(history)


def render_learning_feedback(
    knowledge_base: PrecedentKnowledgeBase,
    report: PolicyPrecedentReport,
) -> None:
    st.markdown("### Stretch 2 - Policy & Precedent Agent + Learning Feedback Loop")
    st.caption(
        "BONUS CAPABILITY - SYNTHETIC OFFLINE RUN. Reviewer-approved corrections enter an "
        "append-only precedent memory and are retrieved as advisory Judge context."
    )
    first, second, third = st.columns(3)
    first.metric("Approved corrections", len(knowledge_base.records))
    second.metric("Matched precedents", len(report.matches))
    third.metric("Authority", "ADVISORY ONLY")
    st.table(feedback_loop_steps(knowledge_base, report))

    if report.matches:
        rows = [
            {
                "Feedback ID": item.feedback_id,
                "Similarity": f"{item.similarity_score}/100",
                "Historical case": item.source_case_id,
                "Rule": ", ".join(item.source_rule_ids),
                "Human correction": item.corrected_status.value,
                "Why": item.correction_reason,
            }
            for item in report.matches
        ]
        st.table(rows)
    else:
        st.info("No approved precedent matches the current dispute type and rule.")
    st.info(report.advisory)
    with st.expander("Advisory context supplied to Judge", expanded=False):
        st.json(report.judge_context)
    st.caption(
        "Boundary: feedback never retrains the model or edits policy automatically. Precedent cannot "
        "change current status, action, or money; the deterministic policy is still authoritative."
    )


def render_judge(case: EvaluatedDemoCase, precedent: PolicyPrecedentReport) -> None:
    st.markdown("### 4 · Judge recommendation")
    st.info(case.judge.reasoning_summary)
    left, right = st.columns([2, 1])
    left.write(f"**Recommended status:** `{case.judge.recommended_case_status.value}`")
    left.write(f"**Recommended action:** {action_text(case.judge.recommended_action)}")
    left.write(f"**Policy citations:** {', '.join(case.judge.policy_citations)}")
    left.write(
        "**Advisory precedent context:** "
        + (", ".join(item.feedback_id for item in precedent.matches) or "No matching precedent")
    )
    right.metric("Judge self-confidence", f"{case.judge.judge_confidence.score}/100")
    right.caption("Uncalibrated model-style self-assessment. Never used as a release threshold.")


def render_gates(case: EvaluatedDemoCase) -> None:
    st.markdown("### 5 · Deterministic hard gates")
    st.table(gate_rows(case))
    if case.evaluation.business_status == BusinessStatus.PENDING_HUMAN_REVIEW:
        st.warning("The system refused to auto-resolve this version because a required gate is blocked.")
    else:
        st.success("All release-relevant deterministic checks passed for this synthetic case version.")


def render_outcome(case: EvaluatedDemoCase, escalation: EscalationPacket) -> None:
    st.markdown("### 6 · Final simulated status and separated confidence signals")
    action = case.evaluation.allowed_action if not escalation.triggered else None
    first, second, third, fourth = st.columns(4)
    first.metric("Final status", final_status_text(case, escalation))
    second.metric("Action", action.type.value if action else "NONE")
    third.metric("Refund", f"SGD {(action.amount_cents if action else 0) / 100:.2f}")
    fourth.metric("Evidence completeness", f"{program_evidence_sufficiency(case)}/100")
    st.caption(
        "Evidence completeness is an uncalibrated, display-only program metric. "
        "Automatic release is controlled only by the deterministic gates above."
    )
    st.markdown(
        '<div class="rr-note"><strong>No real refund or user notification was executed.</strong> '
        "This prototype displays a simulated policy outcome only.</div>",
        unsafe_allow_html=True,
    )


def render_escalation(packet: EscalationPacket) -> None:
    st.markdown("### Stretch 3 - Escalation Protocol")
    st.caption(
        "BONUS CAPABILITY - Judge confidence can trigger a safe human handoff, but it can never "
        "authorize automatic release. Deterministic evidence gates remain authoritative."
    )
    first, second, third = st.columns(3)
    first.metric("Escalation", "TRIGGERED" if packet.triggered else "NOT REQUIRED")
    second.metric("Judge / threshold", f"{packet.judge_confidence} / {packet.threshold}")
    third.metric("Review queue", packet.queue or "NONE")
    if packet.triggered:
        st.warning(" | ".join(packet.trigger_reasons))
    else:
        st.success("No confidence or deterministic review trigger is active for this case version.")
    with st.expander("Human-review handoff packet", expanded=packet.triggered):
        st.write(packet.case_summary)
        st.write("**Evidence IDs:**", ", ".join(packet.evidence_ids))
        st.write("**Matched rules:**", ", ".join(packet.matched_rule_ids) or "None")
        st.write("**Next step:**", packet.recommended_next_step)


def render_notifications(case: EvaluatedDemoCase) -> None:
    st.markdown("### 7 · Separate party notifications")
    rider, driver = st.columns(2)
    with rider:
        with st.container(border=True):
            st.markdown("#### Message to rider")
            st.write(case.judge.rider_explanation)
            st.caption("Simulation only · no message sent")
    with driver:
        with st.container(border=True):
            st.markdown("#### Message to driver")
            st.write(case.judge.driver_explanation)
            st.caption("Simulation only · no message sent")


def render_timeline(
    case: EvaluatedDemoCase,
    collector: EvidenceCollectionReport,
    precedent: PolicyPrecedentReport,
    escalation: EscalationPacket,
) -> None:
    st.markdown("### 8 · Agent and tool timeline")
    st.caption("SYNTHETIC sequence for offline UI validation; these timings are not model latency measurements.")
    timeline = [
        {"Step": "Case snapshot loaded", "Actor": "Python store", "Mode": "SYNTHETIC", "Elapsed": "0.00 s"},
        {
            "Step": "Evidence package prepared",
            "Actor": collector.agent_name,
            "Mode": collector.execution_mode,
            "Elapsed": "0.01 s",
        },
        {"Step": "Evidence subsets selected", "Actor": "Rider / Driver fixtures", "Mode": "SYNTHETIC", "Elapsed": "0.02 s"},
        {
            "Step": "Reviewer feedback retrieved as advisory context",
            "Actor": precedent.agent_name,
            "Mode": precedent.execution_mode,
            "Elapsed": "0.03 s",
        },
        {"Step": "Recommendation record built", "Actor": "Judge fixture", "Mode": "SYNTHETIC", "Elapsed": "0.04 s"},
        {"Step": "Policy and integrity gates evaluated", "Actor": "Python", "Mode": "DETERMINISTIC", "Elapsed": "0.05 s"},
        {
            "Step": "Human handoff evaluated",
            "Actor": escalation.capability_name,
            "Mode": "DETERMINISTIC",
            "Elapsed": "0.06 s",
        },
    ]
    st.table(timeline)


def render_delta(demo: DeltaDemo) -> None:
    st.markdown("### 9 · Decision Delta")
    delta = demo.delta
    before = demo.before.evaluation
    after = demo.after.evaluation
    before_fact = before.facts.get("FACT-GPS-COVERAGE-SUFFICIENT", FactStatus.UNKNOWN).value
    after_fact = after.facts.get("FACT-GPS-COVERAGE-SUFFICIENT", FactStatus.UNKNOWN).value
    comparison: list[dict[str, Any]] = [
        {"Chain link": "Target evidence", "v1": "Not present", "v2": delta.changed_evidence_id},
        {"Chain link": "GPS coverage", "v1": f"{before.metrics['gps_coverage_percent']:.1f}%", "v2": f"{after.metrics['gps_coverage_percent']:.1f}%"},
        {"Chain link": "Verifiable fact", "v1": before_fact, "v2": after_fact},
        {"Chain link": "Matched rule", "v1": ", ".join(before.matched_rule_ids), "v2": ", ".join(after.matched_rule_ids)},
        {"Chain link": "Program status", "v1": before.business_status.value, "v2": after.business_status.value},
        {"Chain link": "Allowed action", "v1": action_text(before.allowed_action), "v2": action_text(after.allowed_action)},
        {"Chain link": "Simulated refund", "v1": "SGD 0.00", "v2": f"SGD {after.allowed_action.amount_cents / 100:.2f}"},
    ]
    st.table(comparison)
    if delta.causal_claim_allowed:
        st.success(delta.display_message)
    else:
        st.error(delta.display_message)
    st.caption(
        "Scope: this claim applies only to the fixed demo policy and the compared synthetic snapshots. "
        "It does not prove real-world causality or fairness."
    )


store = load_store()
delta_demo = load_delta()

st.markdown('<div class="rr-kicker">Evidence-grounded dispute resolution</div>', unsafe_allow_html=True)
st.markdown('<div class="rr-title">RideResolve</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="rr-subtitle">Five-agent reasoning, reviewer-approved precedent memory, deterministic policy gates, and an auditable explanation of exactly when one trusted record changes a simulated ruling.</div>',
    unsafe_allow_html=True,
)
st.markdown('<span class="rr-pill">SYNTHETIC · OFFLINE DEMO</span>', unsafe_allow_html=True)
st.warning(
    "This screen uses synthetic evidence, synthetic feedback, and synthetic Agent records. "
    "It does not claim a live model run or a real platform action."
)

with st.sidebar:
    st.header("Demo controls")
    scenario = st.selectbox(
        "Scenario",
        (
            "Decision Delta · Route Deviation",
            "No-Show · Valid Charge",
            "Route Deviation · Stable Refund Case",
        ),
    )
    if scenario.startswith("Decision Delta"):
        version = st.radio("Case version", ("v1 · incomplete GPS", "v2 · GPS supplemented"))
        case = delta_demo.before if version.startswith("v1") else delta_demo.after
    elif scenario.startswith("No-Show"):
        case = evaluate_demo_case(store, "CASE-NS-TOOL-001", 1)
    else:
        case = evaluate_demo_case(store, "CASE-RD-TOOL-001", 1)
    st.divider()
    st.caption("Execution mode")
    st.markdown("**SYNTHETIC**")
    st.caption("Policy and money are computed by Python. Agent text on this page is a clearly labelled fixture.")

collector = run_evidence_collection_agent(
    store,
    case.snapshot.case_id,
    case.snapshot.case_version,
)
precedent_memory = load_precedent_memory()
precedent = run_policy_precedent_agent(case, precedent_memory)
escalation = build_escalation_packet(case)

render_case_header(case)
render_evidence_collector(collector)
render_evidence(case)
render_advocates(case, collector)
render_learning_feedback(precedent_memory, precedent)
render_judge(case, precedent)
render_gates(case)
render_outcome(case, escalation)
render_escalation(escalation)
render_notifications(case)
render_timeline(case, collector, precedent, escalation)
if scenario.startswith("Decision Delta"):
    render_delta(delta_demo)
else:
    st.markdown("### 9 · Decision Delta")
    st.info("This scenario has no comparable second snapshot. No evidence-caused ruling claim is made.")
