# RideResolve verification and submission status

Last updated: 2026-10-13

## Current verified baseline

- `148` pytest tests pass; `144` are also discoverable through the standard-library `unittest` runner.
- Python compilation passes for `app.py`, `rideresolve/`, `scripts/`, and `tests/`.
- Streamlit interaction tests cover Decision Delta v1, Decision Delta v2, and No-Show.
- A browser-rendered core-demo preview is stored at `docs/streamlit-demo-preview.png`. It predates the three stretch panels and should be refreshed before final submission.
- The application remains an honestly labelled `SYNTHETIC - OFFLINE DEMO`.

## Gate B - Passed for the deterministic MVP scope

Verified behavior includes:

- all eight human-prelabelled Route Deviation and No-Show cases;
- fail-closed policy contracts for rule IDs, evaluators, parameters, and outcomes;
- immutable snapshots, evidence membership, checksums, origin-case binding, and evaluation fingerprints;
- deterministic GPS merge, overlap handling, coverage, distance, and conflict detection;
- authoritative fare-ledger amount derivation;
- No-Show authoritative-source, event-time, contact-window, and coverage rules;
- explicit `NO_ACTION` invariants and Judge/program consistency validation.

## Gate C - Persisted deterministic spine passed

The main pair exists in `data/cases/tool_cases.json`:

- `CASE-RD-001 v1`: 70% GPS coverage, `RD-001`, `PENDING_HUMAN_REVIEW`;
- `CASE-RD-001 v2`: the same business inputs plus one authoritative GPS supplement, 100% GPS coverage, `RD-004`, simulated SGD 3.25 refund;
- `build_decision_delta()` returns `comparable=true`, `causal_claim_allowed=true`, `changed_evidence_id=EV-RD-GPS-SUPPLEMENT`, and `changed_fact_id=FACT-GPS-COVERAGE-SUFFICIENT`.

The permitted claim is deliberately narrow: under the fixed demo policy and fixed other synthetic inputs, the added evidence changed the program-evaluated fact, rule outcome, and simulated ruling. It does not prove real-world causality, fairness, or accuracy.

## Stretch goals - Local implementation passed

### Evidence Collection Agent

- Selects a bounded evidence-source plan from the dispute type.
- Calls the same read-only case, evidence, and policy tools exposed to ADP.
- Returns a shared version-pinned evidence package, query log, citations, and explicit gaps.
- Detects the v1 GPS coverage gap, accepts the v2 supplement, and selects the separate No-Show source plan.
- Cannot determine credibility, liability, status, action, or money.

The fourth role's read-only CloudBase tools and independent credential are deployed. Its tool-free ADP Agent completed the functional five-Agent No-Show workflow using three explicit upstream tool nodes. The result remains functional evidence rather than `LIVE` production data or a verified `REPLAY`.

### Policy & Precedent Agent and Learning Feedback Loop

- Human corrections must represent a genuine outcome change and include a reason, source rule IDs, and evidence citations.
- Approved records are checksum-bound, unique, append-only, and restricted to `ADVISORY_PRECEDENT_ONLY`.
- The fifth Agent retrieves only same-category, overlapping-rule precedents and supplies cited `ADVISORY_ONLY` context to the Judge.
- Route Deviation v2 retrieves two comparable synthetic `RD-004` reviewer corrections; v1 and the default No-Show case correctly retrieve none.
- The current policy evaluation object remains unchanged before and after precedent retrieval.

The knowledge base contains four clearly marked synthetic human-override fixtures: two same-rule Route Deviation records, No-Show coverage, and one historical outcome that conflicts with current policy while remaining advisory only. Eight dedicated tests cover ingestion, persistence, append-only enforcement, genuine-change validation, tamper rejection, relevant retrieval, policy-conflict isolation, and irrelevant-case rejection. The role-isolated policy and precedent bindings and the tool-free fifth ADP Agent completed the functional No-Show run; no approved precedent matched that case.

### Escalation Protocol

- A deterministic review requirement always triggers a human-review packet.
- Judge self-confidence below `70/100` also triggers safe escalation.
- The packet contains the case/version, policy, evidence IDs, matched rules, trigger reasons, review queue, and next step.
- Model confidence can only escalate; it can never release a case or bypass a hard gate.

## Additional MVP evidence sources - Passed locally

- Route Deviation fixtures include authenticated chat with structured synthetic annotations for sentiment, consent, disagreement, and threat.
- Route Deviation and No-Show include `HISTORICAL_BEHAVIOR_PROFILE` evidence with account age, completed-trip count, recent-dispute count, and rating pattern.
- Historical profiles are `SUPPORTING`, displayed as `CONTEXT ONLY`, and excluded from deterministic policy evaluation.
- Regression tests verify that removing historical context does not change business status, matched rule, or action.

The annotations remain `SYNTHETIC`; they do not prove that the cloud workflow emitted these fields.

## Gate A - Functional ADP runs completed; formal sign-off pending

The preserved historical Route Deviation run completed a three-core-Agent workflow:

- Rider and Driver independently called bounded tools and returned cited arguments;
- Judge returned `RESOLVED`, `RD-004`, and a 325-cent SGD full-refund recommendation;
- the JSON parse node and End node kept the result structured.

The newer No-Show run completed the workflow-first target:

- all five Agent nodes had empty tool lists;
- seven explicit, role-scoped workflow tool nodes completed successfully;
- the deterministic gate accepted `RESOLVED / NS-002 / NO_ACTION / 0 SGD`;
- the structured End JSON was preserved;
- the matching CloudBase audit summary contains exactly seven successful HTTP 200 events, the expected call order, unique request IDs, and one server instance.

Together, these artifacts support the statement **functional model/tool workflows completed**. They do not support formal Gate A sign-off because the complete native ADP trace export and the separate Rider/Driver Agent outputs for the No-Show run are unavailable. The run is not labelled `REPLAY`.

Submission-safe screenshots, the No-Show End JSON, their hashes, supported findings, and limitations are indexed under `docs/evidence/` and recorded in `docs/GATE_A_FUNCTIONAL_RUN_REPORT.md`.

## Security status

- The deployed registry contains token hashes rather than raw role credentials. Its current test-window expiry is managed outside the submission repository.
- Raw role tokens remain under ignored local `var/` storage and must be removed from ADP and revoked or rotated in CloudBase before final submission.
- Submission-safe copies of the two development transcripts are stored under `docs/process_records/`.
- Three manually reviewed WorkBuddy screenshots, their written development-process description, and matching SHA-256 approvals are stored under `docs/process_records/submission/`.
- Raw source transcripts outside this repository remain sensitive and must not be submitted.
- `.env`, `var/`, logs, JSONL audit files, caches, and raw credentials are excluded by `.gitignore`.

## Remaining submission P0

1. Refresh `docs/streamlit-demo-preview.png` if a newer product screenshot is required by the submission form.
2. Rehearse the two-minute walkthrough with the stable local synthetic comparison.
3. Complete final repository push, credential rotation, and package generation.

## Optional work after P0

- Obtain the complete native ADP trace export and separate Agent outputs for formal Gate A correlation.
- Create a verified replay only after its complete original source artifacts exist.

These optional tasks must not displace package hygiene, credential cleanup, repository publication, or rehearsal.

## Verification commands

```powershell
python -m scripts.check_no_show_readiness
python -m unittest discover -s tests -v
python -m pytest -q
python -m compileall -q app.py rideresolve scripts tests
python -m streamlit run app.py
```
