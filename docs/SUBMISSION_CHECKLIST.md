# RideResolve submission and live-demo checklist

Freeze product scope after this checklist passes. Fix demonstrated defects only.

## Mandatory eligibility proof

- [x] Capture at least three genuine CodeBuddy or WorkBuddy development-conversation screenshots, or one qualifying screen recording.
- [x] Make the product name, development request, and substantive AI assistance readable.
- [x] Remove or mask API keys, role tokens, deployment credentials, personal identifiers, and unrelated private content.
- [x] Do not use Tencent ADP screenshots as a substitute for CodeBuddy/WorkBuddy proof.
- [x] Add a short written development-process description alongside the screenshots.

Completed on 2026-10-16. The three reviewed screenshots, development-process description, and hash-bound privacy approval are stored under `docs/process_records/submission/`.

## Submission copy

- [x] Project title: `RideResolve`.
- [x] Short blurb contains fewer than 10 English words.
- [x] Project description includes Overview, Real-World Scenario Insights, Comprehensive Solution Design, prompt design, and Business Value.
- [x] Decision Delta is presented as the primary differentiator.
- [x] Evidence Collection, Policy & Precedent, Learning Feedback, and Escalation are presented as locally implemented stretch capabilities.
- [x] All five Agents are described only as a successful functional ADP run, not as a formal Gate A pass or a `REPLAY` dataset.
- [x] No unsupported production accuracy, savings, fairness, or latency claims are included.

## Repository package

- [x] Repository opens with `README.md` and `docs/assets/rideresolve-cover-384x216.png`.
- [x] Include `app.py`, `rideresolve/`, `data/`, `docs/`, `scripts/`, `tests/`, `pyproject.toml`, and the workflow-first manifest/setup guide.
- [x] Include the architecture diagram, two-minute walkthrough, Agent prompts, and source code.
- [x] Exclude `var/`, `.env`, raw credentials, raw development transcripts, caches, generated logs, raw CloudBase API responses, and JSONL audit files.
- [x] Include only three or more manually reviewed, submission-safe CodeBuddy/WorkBuddy screenshots; exclude the two full transcript exports even after automated redaction.
- [x] Confirm the application still says `SYNTHETIC - OFFLINE DEMO`.
- [x] Refresh `docs/streamlit-demo-preview.png`; the current 2026-10-15 capture shows the five-Agent stretch interface.
- [x] Confirm the wording says simulated resolution and does not imply a real refund or notification.
- [x] Describe the historical three-core-Agent Route Deviation run and the newer five-Agent workflow-first No-Show run as functional demonstrations with formal artifact sign-off pending.
- [x] Describe v0.6 as natural-language Intake plus a strictly serial five-Agent workflow; never ask an end user to provide `run_id`.
- [x] Mark `docs/adp/multiagent_manifest.json` as an unvalidated experiment and the root orchestration import ZIP as legacy.

## Final local verification

Run from the repository root:

```powershell
python -m scripts.check_no_show_readiness
python -m unittest discover -s tests -v
python -m pytest -q
python -m compileall -q app.py rideresolve scripts tests
python -m streamlit run app.py
```

Expected automated result: `148` pytest tests and `144` unittest tests pass, `pip check` reports no broken requirements, and compilation exits successfully.

Then confirm in a fresh browser session:

- [ ] the page loads without a Python traceback;
- [ ] v1 shows 70% GPS, `RD-001`, pending review, `NEEDS SUPPLEMENT`, and an escalation packet;
- [ ] v2 shows 100% GPS, `RD-004`, simulated SGD 3.25, `READY`, and no escalation;
- [ ] v2 retrieves one advisory `RD-004` feedback record while v1 and No-Show retrieve none;
- [ ] only `EV-RD-GPS-SUPPLEMENT` appears as changed evidence;
- [ ] No-Show shows `NS-002 / NO_ACTION / 0 cents` and the No-Show collector plan;
- [ ] evidence provenance, five Agent roles, feedback loop, Judge output, hard gates, notifications, timeline, escalation, and Delta render;
- [ ] the cover and preserved ADP evidence images open from the repository.

## Two-minute judging path

1. Open Route Deviation v1 and show that incomplete evidence blocks automatic resolution.
2. Show the Evidence Collection Agent detecting the 70% GPS gap and producing a shared evidence package.
3. Show the independent Rider and Driver panels plus one provenance record.
4. Show the Escalation Protocol's complete human-review handoff.
5. Switch to v2 and point to the single GPS supplement.
6. Show the matching reviewer correction and emphasize that it is advisory, not copied into the current ruling.
7. Show `RD-004`, the ledger-derived SGD 3.25 amount, and the cleared escalation trigger.
8. Finish on Decision Delta: evidence, fact, rule, action, and simulated money.

Do not run two live model versions inside the main pitch. The stable local synthetic comparison is the primary story; preserved ADP screenshots separately demonstrate the historical three-core-Agent run and the workflow-first five-Agent No-Show run.

## Claims to use

- "The model recommends; deterministic code controls evidence integrity, policy, escalation, status, and simulated money."
- "The Evidence Collection Agent prepares one immutable evidence baseline and reports gaps before either side argues."
- "Human corrections enter an append-only precedent memory; the fifth Agent supplies advisory context but cannot rewrite policy."
- "Low model confidence may trigger human review, but high confidence can never bypass a hard gate."
- "Decision Delta verifies what changed under this fixed demo policy and fixed other inputs."
- "Missing or conflicting evidence routes to review instead of being treated as proof of absence."

## Claims to avoid

- Do not claim real-world fairness, causal truth, production accuracy, legal finality, real refunds, or real notifications.
- Do not call synthetic records `LIVE` or `REPLAY`.
- Do not claim formal Gate A completion or call the five-Agent cloud result `REPLAY`; only the functional workflow is demonstrated.
- Do not claim formal Gate A completion without the strict artifact-verifier result.
- Do not claim that more Agents automatically improve correctness; point to the narrow responsibility boundaries.

## Cloud evidence completed before submission

- [x] Deploy all five tool-free Agent nodes plus seven explicit role-scoped workflow tool nodes.
- [x] Run and archive one functional No-Show workflow.
- [x] Preserve the structured End JSON and matching seven-event CloudBase audit summary.
- [ ] Preserve a complete native ADP trace export and separate Rider/Driver outputs for formal Gate A verification.
- [ ] Relabel records as `REPLAY` only after their complete source artifacts pass verification.

## Cleanup after any cloud run

- [ ] revoke the local manifest;
- [ ] remove role credentials from ADP;
- [ ] rotate or remove the CloudBase deployment registry;
- [ ] disable public test traffic;
- [ ] scan every exported artifact for secrets before copying it into the repository.
