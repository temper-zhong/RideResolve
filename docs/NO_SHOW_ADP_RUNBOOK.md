# No Show ADP workflow-first run checklist

This runbook is the minimum safe path for obtaining a No-Show run with five tool-free Agents and
seven explicit workflow tool nodes. It does not create credentials during preparation and does
not change the current deterministic baseline.

## Expected result

The official synthetic input is `CASE-NS-TOOL-001` version `1` under `DEMO_POLICY_V1`. The deterministic evaluator expects:

```json
{
  "business_status": "RESOLVED",
  "matched_rule_ids": ["NS-002"],
  "allowed_action": {
    "type": "NO_ACTION",
    "fee_item": null,
    "amount_cents": 0,
    "currency": "SGD"
  }
}
```

The Judge may explain the result in different words, but its structured status, policy citation, and action must agree with this result. Its self-reported confidence is uncalibrated and must not control release.

## Phase 1 local readiness

Run this before opening a public test window:

```powershell
python -m scripts.check_no_show_readiness
python -m unittest discover -s tests -v
```

The first command must return `ready: true` and `credentials_issued: false`. Do not proceed if the deterministic result differs from `NS-002 / NO_ACTION`.

## Phase 2 provider cleanup

1. Remove or rotate every old role credential still configured in ADP or CloudBase.
2. Confirm CloudBase minimum and maximum instances are both `1`.
3. Confirm the deployed tool service is private or has public traffic disabled while configuring it.
4. Confirm CloudBase structured stdout capture is enabled for the test window.

Local registry revocation does not revoke credentials already embedded in a deployed environment.

## Phase 3 issue one short lived run

Only when CloudBase and ADP are ready, run:

```powershell
python scripts/create_probe_run.py --case-id CASE-NS-TOOL-001 --case-version 1 --ttl-seconds 1800 --max-requests-per-role 12
```

This creates an ignored local credential file and a Base64 deployment registry containing token hashes. Never paste the raw credential file into a prompt, chat, screenshot, repository, or submission package.

Configure the deployed service with:

- `RIDERESOLVE_RUN_REGISTRY_B64`: the generated hashed single-run registry;
- `RIDERESOLVE_SINGLE_INSTANCE_ACK=MIN_1_MAX_1_CONFIRMED` only after visually confirming the instance limits;
- the real controlled HTTPS origin when regenerating the OpenAPI document.

Configure the seven workflow tool nodes and four used credential roles exactly as recorded in
`adp/WORKFLOW_FIRST_MIGRATION.md`. Put each short-lived `X-RideResolve-Run-Token` only in the
matching workflow node's masked APIKey field. All five Agent tool lists must be empty; do not
configure or expose the unused Judge credential.

## Phase 4 verify response mapping before the workflow

In each workflow tool-node tester, confirm the useful payload reaches the mapped `result` object
rather than appearing only in a platform-specific `original` field. Stop if ADP displays an
empty mapped `response` or the downstream Agent cannot read returned evidence IDs.

The model-visible start input must contain only:

```json
{"run_id":"RUN-..."}
```

It must not contain evidence, case facts, policy text, or a role token.

## Phase 5 execute once and capture before closing

1. Run the complete workflow-first graph once, including all five tool-free Agents.
2. Export the complete, untruncated ADP trace.
3. Save the raw End JSON as one object, not an escaped JSON string.
4. Save both Advocate final structured outputs.
5. Export the matching CloudBase JSONL audit before the container is replaced.
6. Record the platform request ID, platform trace ID, non-secret `run_id`, and workflow timestamps.
7. Confirm the run finishes within 120 seconds from workflow start through the Python gate.

Do not rerun until the model produces the expected answer. A mismatch is evidence to diagnose, not a result to hide.

## Phase 6 deterministic acceptance

The run passes only if:

- the Rider and Driver workflow nodes each called `get_trip_evidence`, and each Advocate cited
  only IDs returned to its role;
- the trace contains exactly seven successful workflow tool-node calls and no tool call nested
  under an Agent;
- the Judge cites evidence in the snapshot and policy IDs in `DEMO_POLICY_V1`;
- the Judge result agrees with `NS-002 / NO_ACTION / 0 cents`;
- every successful ADP tool request matches one CloudBase audit event by request ID, role, operation, returned IDs, and time window;
- exactly one tool server instance ID appears;
- the strict Python gate and artifact verifier both pass.

If the trace or audit export is incomplete, record the run as functional evidence only. Do not label it a formal Gate A pass or a Streamlit `REPLAY`.

## Phase 7 cleanup

Immediately after capture:

1. revoke the local run manifest;
2. remove all workflow-node role credentials from ADP;
3. remove or rotate the CloudBase deployment registry;
4. disable public traffic to the test service;
5. retain only redacted evidence and hashes in the submission repository.
