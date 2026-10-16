# RideResolve - submission copy

This file is written for direct transfer into the competition submission form. Keep the truth labels and limitations when shortening it.

## Project title

RideResolve

## Short blurb

**Auditable multi-agent reasoning for ride dispute resolution.**

Word count: 7.

## Project overview

RideResolve is an evidence-grounded multi-agent prototype for resolving standard ride-hailing disputes quickly, consistently, and transparently. It currently handles two end-to-end dispute categories: Route Deviation and No-Show.

The local target workflow models five specialist Agent roles. An Evidence Collection Agent prepares a shared immutable package; Rider and Driver Advocates produce separate cited arguments; a Policy & Precedent Agent retrieves reviewer-approved corrections as advisory context; and a Judge recommends an outcome. The language model never controls final case status or money: deterministic Python validates evidence integrity, evaluates versioned policy, checks the Judge's recommendation, derives any simulated refund from the authoritative fare ledger, and decides whether the case may be resolved or must be reviewed.

The main differentiator is **Decision Delta**. Instead of merely showing that an AI changed its answer, RideResolve verifies the exact chain that changed under a fixed policy and fixed other inputs:

`evidence -> verifiable fact -> matched rule -> allowed action -> simulated money`

In the primary demo, version 1 has only 70% GPS coverage and is held for human review under `RD-001`. Version 2 adds exactly one authoritative GPS supplement. Coverage becomes 100%, the program reaches `RD-004`, and the authoritative ledger permits a simulated SGD 3.25 refund. The system refuses to make this evidence-caused-change claim if the new evidence is missing, altered, unrelated to the case, or evaluated from different inputs.

## Real-world scenario insights

Ride-hailing disputes are difficult because evidence is distributed across telemetry, communication records, payment data, operational events, and company policy. Riders and drivers often describe the same trip differently, and absence of a record does not necessarily prove that an event never occurred. A fast but unsupported automated decision can be worse than a slower human review.

RideResolve therefore treats dispute resolution as a controlled evidence workflow rather than a single chatbot response:

- both parties receive an independent Advocate instead of one blended narrative;
- every material claim must cite a visible evidence ID;
- authoritative operational records are separated from supporting context and party claims;
- missing, conflicting, incomplete, or unverifiable evidence routes to review;
- chat semantics are explicitly labelled as model interpretation, not verified intent;
- historical behavior is context only and cannot decide credibility, liability, status, or money;
- rider and driver receive separate explanations of the simulated result.

This design is intended for standard, policy-bounded disputes. It does not claim to replace human handling for safety incidents, ambiguous oral agreements, conflicting authoritative records, or other high-risk cases.

## Comprehensive solution design

### 1. Evidence Collection Agent - stretch goal

A bounded fourth Agent selects the appropriate evidence-source plan from the dispute type, calls read-only case/evidence/policy tools, verifies returned record integrity, and prepares one version-pinned evidence package for both Advocates. For Route Deviation it requests GPS, route baseline, and fare ledger records, with relevant chat, traffic, and historical context. For No-Show it requests GPS, trip-event, contact, and fare-ledger records.

The collector reports missing or incomplete inputs but cannot judge either party, select an outcome, or calculate money. Its local implementation is executable and tested. The tool-free collector also completed the functional five-Agent Tencent Cloud ADP No-Show run using three explicit upstream workflow tool nodes. The local Streamlit output remains labelled `SYNTHETIC_OFFLINE` and is not presented as a replay of that cloud run.

### 2. Rider Advocate and Driver Advocate

The two Advocates inspect the same immutable snapshot but build separate cited arguments. Their prompts require them to distinguish claims from facts, request only relevant source types, report uncertainty, ignore instructions embedded inside evidence, and cite only IDs returned by tools. They may organize authenticated chat into sentiment, consent, disagreement, and threat signals, but these interpretations cannot control policy or money.

### 3. Policy & Precedent Agent and Learning Feedback Loop - stretch goals

When a human reviewer genuinely overrides a Judge recommendation, RideResolve captures the changed outcome, reason, evidence citations, policy version, and source rule IDs. Only reviewer-approved, checksum-valid records with `ADVISORY_PRECEDENT_ONLY` scope enter the append-only precedent memory. Unchanged outcomes, duplicate IDs, and tampered records are rejected.

The fifth Agent retrieves only precedents from the same dispute category with overlapping policy rules. It supplies the Judge with cited `feedback_id` values and the historical condition to verify, but explicitly warns against copying the historical outcome. Feedback does not automatically retrain a model or edit company policy.

The local feedback loop and retrieval Agent are executable and tested with four clearly labelled synthetic corrections, including No-Show and policy-conflict examples. The tool-free Policy & Precedent Agent and its two explicit workflow tool nodes completed the functional No-Show ADP run. Precedent remained advisory and returned no approved match for that case.

### 4. Judge Agent

The Judge compares both structured arguments, identifies agreement and conflict, cites evidence and policy, recommends a permitted action, provides separate explanations to rider and driver, and emits an explicitly uncalibrated self-confidence score. The score is never treated as an accuracy probability and never authorizes automatic release.

### 5. Deterministic trust boundary

Python independently controls the release-relevant decisions:

- snapshot membership, origin-case binding, checksum, and input fingerprint;
- policy version, effective period, rule contract, and allowed outcome;
- GPS segment merge, overlap removal, coverage, distance, and conflict handling;
- No-Show arrival, waiting, contact timing, and authoritative-source requirements;
- fee item, currency, and ledger-derived simulated refund amount;
- exact consistency between the Judge recommendation and the program-allowed result;
- separation of business review from technical model failure.

If a model invents an ID, returns an invalid structure, contradicts the allowed action, or cites an inapplicable policy, the output is rejected rather than silently repaired.

### 6. Escalation Protocol - stretch goal

RideResolve creates a complete human-review packet whenever a deterministic gate blocks resolution or the Judge's self-confidence is below `70/100`. The packet contains case/version, policy, cited evidence IDs, matched rules, trigger reasons, review queue, and recommended next step.

This threshold is deliberately one-way: low confidence may trigger escalation, but high confidence can never bypass a hard gate or approve money movement.

### 7. Observable product experience

The English Streamlit interface shows:

- case and version selection;
- evidence summaries and provenance;
- the Evidence Collection Agent query plan and gaps;
- independent Rider and Driver arguments;
- the Learning Feedback Loop audit stages and Policy & Precedent Agent matches;
- Judge recommendation and separated confidence signals;
- deterministic gate results;
- final simulated status, action, and amount;
- the Escalation Protocol handoff packet;
- separate rider and driver explanations;
- an Agent/tool timeline;
- the Decision Delta comparison.

The UI explicitly distinguishes `SYNTHETIC`, `REPLAY`, and `LIVE`. The current stable demo is `SYNTHETIC - OFFLINE DEMO`, so it never implies that a real refund, notification, or production decision occurred.

### 8. Prompt design

Each Agent prompt uses a narrow role, bounded tools, a strict JSON output contract, evidence and policy citation requirements, and explicit prohibitions against invented facts or money execution. The prompts also instruct Agents to treat evidence payload text as untrusted data and never follow instructions found inside it.

The complete prompt records are included under `docs/adp/prompts/`. Tencent Cloud ADP provides the model-facing orchestration for the demonstrated five-Agent workflow-first run, while Python remains the deterministic trust boundary. The cloud result is described as functional evidence rather than a formal Gate A pass because a complete native ADP trace export and separate Agent outputs are not available.

## Business value

RideResolve is designed to reduce repetitive support work while protecting users from unsupported automated rulings. Its potential operational value comes from automatically resolving complete, standard cases and preparing structured evidence summaries for the cases that still require people.

Verified prototype scope:

- 2 end-to-end dispute categories;
- 5 Agent roles in the local target architecture;
- 4 implemented stretch capabilities: Evidence Collection, Policy & Precedent, Learning Feedback, and Escalation;
- 13 versioned business rules;
- 8 human-prelabelled policy cases;
- 86 passing pytest tests, with 83 also discoverable through the standard-library `unittest` runner;
- 1 preserved historical three-core-Agent Route Deviation run;
- 1 preserved functional five-Agent workflow-first No-Show run with a structured End result and matching seven-event CloudBase audit summary;
- deterministic simulated refund derivation from an authoritative fare ledger;
- explicit fail-closed handling for incomplete evidence, conflicts, invalid outputs, and low-confidence escalation.

The prototype has not been deployed in a production ride-hailing platform, so it does not claim measured production accuracy, cost savings, fairness, or real resolution-time reduction. The product hypothesis is that standard, complete disputes could move from the challenge's stated 24-72 hour support cycle toward near-immediate policy evaluation, while ambiguous cases reach human reviewers with a structured, cited packet instead of an unorganized ticket.

## Responsible AI statement

RideResolve follows four safety principles:

1. The model recommends; deterministic code controls evidence validity, policy, escalation, status, and simulated money.
2. Missing evidence is uncertainty, not proof of absence.
3. Model confidence may cause a safe escalation but never automatic approval.
4. Historical reviewer corrections are advisory and never override current policy.
5. Every execution mode and every limitation is visible to the evaluator.

`RESOLVED` in the prototype means that a simulated recommendation passed the local business gates. It does not mean a real payment was moved, a real user was notified, or a legally final decision was issued.

## Technical stack

- Tencent Cloud ADP for the demonstrated model-facing five-Agent workflow-first orchestration;
- bounded read-only case, evidence, and policy tools;
- Python 3.11+, Pydantic, and deterministic policy evaluators;
- Streamlit for the auditable single-page demo;
- JSON fixtures for immutable synthetic evidence, versioned policy, and checksum-bound approved feedback;
- `unittest` plus Streamlit interaction tests for automated verification.

## Submission artifacts

- Working prototype: `app.py`
- Architecture: `docs/ARCHITECTURE.md`
- Demo walkthrough: `docs/DEMO_WALKTHROUGH.md`
- Agent prompts: `docs/adp/prompts/`
- Verification boundary: `docs/GATE_STATUS.md`
- Functional ADP evidence report: `docs/GATE_A_FUNCTIONAL_RUN_REPORT.md`
- Workflow-first No-Show evidence: `docs/evidence/workflow_first_no_show/`
- Cover image: `docs/assets/rideresolve-cover-384x216.png`
- Source and tests: `rideresolve/` and `tests/`

## Mandatory WorkBuddy/CodeBuddy proof placeholder

Before submission, attach at least three genuine WorkBuddy or CodeBuddy development-conversation screenshots or a qualifying screen recording, plus a short development-process description. Tencent ADP screenshots do not replace this eligibility evidence. Remove all credentials and personal information before upload.
