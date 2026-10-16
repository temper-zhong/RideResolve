# ADP performance pass 1 (accuracy-preserving)

> Historical record: this Agent-owned-tool optimization is superseded by
> `WORKFLOW_FIRST_MIGRATION.md`. Do not apply its Agent tool-binding instructions to the target
> workflow. The baseline timings and observed failure modes remain useful evidence.

Baseline: the successful five-Agent Route Deviation run on 2026-10-12 completed in 164.3s
and produced the expected `RD-004` full refund of SGD 3.25. This pass must preserve that
status, action, amount, policy citation, and determinative evidence citations.

## Invariants

- Keep all five Agent roles.
- Evidence Collection, Rider Advocate, Driver Advocate, and Policy & Precedent must still make
  real native tool calls.
- Rider and Driver must independently select their relevant evidence types.
- Judge remains tool-free in this bounded workflow.
- Deterministic Gate remains authoritative for status, action, currency, and amount.
- Do not describe fixed prefetching or scripted retrieval as autonomous evidence collection.

## Pass-1 workflow calls

| Node | Required successful calls | Removed duplicate |
|---|---|---|
| Evidence Collection | snapshot x1, evidence x1, policy x1 | none |
| Rider Advocate | evidence x1 | snapshot x1 |
| Driver Advocate | evidence x1 | snapshot x1 |
| Policy & Precedent | policy x1, precedents x1 | snapshot x1 and failed policy retry |
| Judge | none | none |

Expected total: seven successful tool calls, down from eleven attempts in the baseline trace.

## Deployment order

The API request contract changes in this pass. Apply it in this exact order so the old CloudBase
service never receives a prompt-generated `scope` field that it does not understand:

1. Deploy `dist/rideresolve-cloudbase-v0.3.1.zip` as the next CloudBase revision while retaining
   the existing protected environment-variable values and the single-instance setting.
2. Confirm `/health` succeeds on the new revision.
3. Re-import or edit only the Evidence and Policy tool definitions from
   `api/rideresolve-tools.openapi.json` so `get_policy_rules` requires
   `scope="APPLICABLE_DISPUTE"`.
4. Update the five ADP node prompts and variable mappings recorded below.
5. Apply the conservative reply limits, save the workflow, and start the three-run acceptance test.

Do not update the ADP prompts before step 1. The previously deployed service rejects unknown
request fields, so sending `scope` to that revision can return HTTP 422.

## ADP variable mappings

- Rider `case_input` <- `SYS.UserQuery`
- Rider `evidence_package` <- `Evidence Collection.Output.Content`
- Driver `case_input` <- `SYS.UserQuery`
- Driver `evidence_package` <- `Evidence Collection.Output.Content`
- Judge `case_input` <- `SYS.UserQuery`
- Judge `evidence_package` <- `Evidence Collection.Output.Content`
- Judge `rider_argument` <- `Rider Advocate.Output.Content`
- Judge `driver_argument` <- `Driver Advocate.Output.Content`
- Judge `precedent_advisory` <- `Policy and Precedent.Output.Content`

Use the launch prompts in `docs/adp/prompts/`. The optimized Evidence package now includes
`run_id` and `dispute_type`, so the Advocates no longer need a separate snapshot call.

## Initial reply limits

Use conservative ceilings for the first validation run:

| Node | Maximum reply tokens |
|---|---:|
| Evidence Collection | 1200 |
| Rider Advocate | 1500 |
| Driver Advocate | 1500 |
| Policy & Precedent | 1000 |
| Judge | 1200 |

Do not start at 600 tokens. Any truncated JSON, missing closing brace, missing citation list, or
Deterministic Gate parse failure is a failed optimization and requires restoring the previous
ceiling.

## Acceptance test

Run the same Route Deviation case three times. Every run must satisfy all of the following:

1. Evidence package is `READY` and contains the seven expected evidence IDs.
2. Rider and Driver each make exactly one successful `get_trip_evidence` call.
3. Policy makes exactly one successful `get_policy_rules` call and one successful
   `search_precedents` call, with no warning retry.
4. Judge returns `RESOLVED`, `REFUND_DISPUTED_FEE_FULL`, `distance_surcharge`, 325 cents,
   SGD, and cites `RD-004`.
5. Deterministic Gate succeeds without repairing or altering the Judge result.
6. No Agent invents an evidence ID or cites an ID absent from the shared package.
7. Record total time, per-node time, input/output tokens, tool attempts, and failed calls.

The first target is a stable runtime below 120 seconds. Only after this pass is stable should a
second pass reduce prompt/tool-schema size or lower reply ceilings further.

## Local verification status

- Focused tool/API suite: 25/25 passed, including explicit policy scope, audit logging, role
  isolation, OpenAPI parity, and request-limit behavior.
- Broader bundled-runtime discovery: 75 tests passed. Two additional test modules could not be
  imported because that runtime does not contain the optional `pytest` and `streamlit` packages;
  there were no failed policy, Delta, tool, or deterministic-gate assertions.
- Deployment archive: `dist/rideresolve-cloudbase-v0.3.1.zip`.
- Archive SHA-256: `EC42B41DEE07BF90A8150F15D818EE2B824572FD9A5B3C8C3114A4D78D4FE044`.
