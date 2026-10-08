# Gate validation status

Last updated: 2026-10-07

## Gate A - Approved probe in progress; not passed and not a baseline change

The ADP Rider Advocate, Driver Advocate, and Judge workflow completed one real-model orchestration smoke run with valid structured outputs and the expected synthetic `RD-004` recommendation. That run supplied evidence directly in the user input and therefore does not satisfy the autonomous-tool-use gate.

The local read-only probe service is now implemented and tested for:

- immutable case snapshot lookup;
- snapshot-scoped evidence lookup with verified checksums;
- versioned policy-rule lookup;
- short-lived, role-specific run tokens whose raw values are not persisted in the registry or audit log;
- server-side run manifests binding one case, version, policy, expiry, role, and request budget;
- omission of evidence IDs from the case-summary response;
- separate Rider and Driver evidence-return audits;
- structured JSONL tool audit and single-server-instance correlation;
- server-generated request IDs that ignore untrusted `X-Request-Id` input;
- a fail-closed container startup acknowledgement for minimum and maximum instance counts of one;
- probe verification that rejects citations not returned to that same role in that run;
- strict request schemas and prompt-injection-like input rejection;
- fixed-HTTPS OpenAPI 3.0 export for ADP.

Gate A still requires:

- public HTTPS deployment of the tool service;
- importing the generated OpenAPI schema into ADP;
- a real Rider and Driver run that autonomously selects and calls tools;
- captured tool traces, timeout behavior, citation validation, and elapsed time.

No mock model response is counted as Gate A evidence. Synthetic case data remains clearly labelled and is valid for the first end-to-end tool-call test. Raw role tokens must remain in ignored local credential files or masked ADP authorization fields and must not be committed or pasted into chat.

## Gate B - Deterministic sample core and reviewed contracts pass

The following claims are supported by automated tests:

- all eight human-prelabelled Route Deviation and No-Show fixtures produce their expected deterministic outcomes;
- policy loading fails closed if the implemented rule IDs, evaluators, parameters, or allowed outcomes diverge from `DEMO_POLICY_V1.json`;
- immutable evidence is selected through the current snapshot's `evidence_refs`, including v2 reuse of the v1 fare ledger;
- evidence checksums are recomputed before evaluation, and missing, duplicate, cross-case, or checksum-mismatched evidence is treated as an integrity failure;
- every policy evaluation carries a fingerprint of the exact snapshot, referenced evidence entities, and policy used to compute it;
- GPS merge, overlap deduplication, coverage, Haversine distance, and same-time conflict handling are deterministic;
- refund amounts come from one non-conflicting authoritative fare ledger;
- No-Show GPS, event, and contact evidence must be authoritative; waiting time is derived from event timestamps; contact coverage must span the waiting interval; and only in-app attempts inside that interval count;
- `NO_ACTION` and Judge-versus-program consistency contracts are enforced.

This is not a claim that every malformed-input and runtime-failure path in the v1.5 plan is complete. Gate B should remain qualified until the remaining fault matrix is implemented.

Evidence checksums provide post-ingestion tamper detection in this prototype. They do not independently prove that an external source is genuine.

## Gate C - Deterministic and synthetic-Judge spine passes; real model pending

The tested Decision Delta path is:

- v1 GPS coverage: 70%;
- v2 GPS coverage after one authoritative supplement: 100%;
- v1: `PENDING_HUMAN_REVIEW` under `RD-001`;
- v2: `RESOLVED` with a SGD 3.25 simulated distance-surcharge refund under `RD-004`;
- one real evidence entity must be added, its checksum and lineage must validate, and it must be an authoritative GPS supplement;
- both deterministic evaluations must be fingerprint-bound to the exact compared inputs;
- nonexistent evidence, a stale evaluation, or a Judge mismatch disables the causal claim;
- GPS or fare-ledger conflicts route to human review.

The permitted wording remains narrow: under the fixed demo policy and fixed other business inputs, the added evidence changed the program-evaluated fact, rule outcome, and simulated ruling. This does not establish real-world causality or fairness.

Gate C is not complete until Gate A is available and real model recommendations pass the same consistency checks without retry cherry-picking.

## Verification

From the `rideresolve` directory:

```powershell
python -m unittest discover -s tests -v
python -m compileall -q rideresolve tests
```

Current result: 42 tests passed; compilation check passed.
