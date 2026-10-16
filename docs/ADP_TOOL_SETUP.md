# ADP Gate A probe runbook

## Authorization boundary

This runbook applies only to the approved, maximum-three-hour CR-001 Gate A probe. It does not approve the hybrid architecture as the formal baseline.

The service contains synthetic, read-only data. It cannot access real accounts, maps, payments, refunds, notifications, files, shell commands, or arbitrary network targets.

## Before deployment

1. Run all tests; all must pass.
2. Do not create the short-lived run until the CloudBase Run service is ready for configuration.
3. Create the run locally with `scripts/create_probe_run.py`.
4. Keep the raw credential file under ignored `var/probe_credentials` and never paste it into chat, prompts, tool descriptions, screenshots, or source control.
5. Configure CloudBase Run with the generated hashed registry Base64 value. The deployment receives token hashes, not raw role tokens.
6. Use exactly one container instance for this short probe. A server restart or multiple observed instance IDs invalidates the probe evidence.

## Deployment constraints

- Deploy the supplied `Dockerfile` to a controlled Tencent CloudBase Run test service.
- Allow public access only for the test window; use the platform default HTTPS domain.
- Set `RIDERESOLVE_RUN_REGISTRY_B64` to the locally generated hashed registry value.
- Set minimum and maximum instances to 1 for the probe.
- Only after visually confirming both values are 1, set `RIDERESOLVE_SINGLE_INSTANCE_ACK=MIN_1_MAX_1_CONFIRMED`; the container refuses to start without this acknowledgement. This is an operator guard, not proof of the cloud setting.
- Keep CloudBase structured stdout logs for the test window.
- Audit logs contain only allowlisted counts and enums; do not weaken this to raw request-body logging.
- Do not import a Schema containing `REPLACE_WITH_DEPLOYED_HOST`.
- After the real HTTPS origin is known, regenerate the OpenAPI document with:

```powershell
python scripts/build_openapi.py --server-url https://ACTUAL_CONTROLLED_HOST
```

## ADP workflow credential setup

Import the five workflow-scoped OpenAPI documents under `api/adp/` instead of
giving every role the complete service document:

| ADP custom tool | OpenAPI document |
|---|---|
| RideResolve Evidence Tools | `rideresolve-evidence-tools.openapi.json` |
| RideResolve Rider Tools | `rideresolve-rider-tools.openapi.json` |
| RideResolve Driver Tools | `rideresolve-driver-tools.openapi.json` |
| RideResolve Policy Tools | `rideresolve-policy-tools.openapi.json` |
| RideResolve Deterministic Gate Tools | `rideresolve-gate-tools.openapi.json` |

All five documents use the same CloudBase `0.5.0` server and API-key header,
but expose only the operations authorized for that workflow role. The Gate document is used only
by workflow tool nodes; do not attach it to the Judge Agent.

Every newly created run issues five independent, short-lived role credentials. Configure the
role-specific APIKey only on the corresponding workflow tool nodes. Agents must have empty tool
lists and must never receive a credential as an input variable:

| Workflow tool nodes | Header | Credential source |
|---|---|---|
| Evidence snapshot/evidence/policy | `X-RideResolve-Run-Token` | local Evidence Collection token |
| Rider evidence | `X-RideResolve-Run-Token` | local Rider token |
| Driver evidence | `X-RideResolve-Run-Token` | local Driver token |
| Policy rules/precedents | `X-RideResolve-Run-Token` | local Policy & Precedent token |
| Deterministic evaluation/final validation | `X-RideResolve-Run-Token` | local Judge token |

The Judge Agent performs no HTTP call. Its credential is configured only on the two workflow-owned
Gate nodes and is never mapped into an Agent input.
Confirm in ADP that authorization values are masked and do not appear in the model prompt, tool
description, node input/output, or exported trace. If this cannot be demonstrated, stop the
experiment. The complete node order, fixed bodies, and variable mappings are in
`adp/ACCURACY_FIRST_DEPLOYMENT.md` and `adp/accuracy_first_manifest.json`.

The role credential and workflow tool layer does not by itself prove a five-Agent ADP run. The
existing Gate A artifact verifier continues to validate the already established core
Rider/Driver/Judge run until the two optional ADP nodes are run and the five-role artifact checks
are completed.

Server-side operation permissions are fail-closed:

| Role | Allowed operations |
|---|---|
| Evidence Collection | `get_case_snapshot`, `get_trip_evidence`, `get_policy_rules` |
| Rider Advocate | `get_trip_evidence` |
| Driver Advocate | `get_trip_evidence` |
| Policy & Precedent | `get_policy_rules`, `search_precedents` |
| Judge workflow Gate | `get_deterministic_evaluation`, `validate_recommendation` |

`get_deterministic_evaluation` returns the authoritative result from version-locked Python policy
code. `validate_recommendation` returns HTTP 409 if the Judge changes the run ID, citations,
status, rule, action, fee item, amount, or currency. Neither operation is available to the model.

`search_precedents` derives the case, policy version, dispute type, and matched rule IDs on the server. The model may supply only `limit` from 1 to 3. Any attempt by the Policy & Precedent Agent to read raw trip evidence, or by another role to search precedents, returns HTTP 403 and is audited.

`get_policy_rules` uses one explicit input, `scope="APPLICABLE_DISPUTE"`. The server still
derives the case, case version, dispute type, and policy version from the signed run credential;
the scope value exists only to avoid ambiguous empty-body tool calls in ADP. It cannot widen the
authorized policy scope.

## Model-visible input

The initial model-visible input contains only the non-secret `run_id`; it must not contain case evidence or any role token:

```json
{"run_id":"RUN-..."}
```

`get_case_snapshot` intentionally omits evidence IDs. Each Advocate receives the successful
output of its own role-scoped workflow `get_trip_evidence` node before it may cite an evidence ID.

## Passing evidence

The probe passes only when all of the following are captured under one `run_id`:

- Rider and Driver each have a successful, role-specific `get_trip_evidence` request;
- each Advocate's citations are a non-empty subset of evidence IDs returned to that same role in this run;
- the Judge End output is one JSON object, not an escaped JSON string;
- the Python deterministic gate accepts the Judge recommendation;
- ADP exported records prove 3–7 model calls and include all three roles;
- every ADP tool record matches a Python audit event by request ID, role, operation, returned IDs, and time window;
- the interval from ADP workflow start through Python gate completion is at most 120 seconds;
- tool audit request IDs are unique and exactly one server instance ID is observed;
- the raw ADP export and raw End output are preserved with SHA-256 hashes; the ADP export origin is separately reviewed against its platform trace/request IDs;
- no credential appears in model-visible data or exported logs.

The service ignores every caller-supplied `X-Request-Id` and generates an `rr-<32 lowercase hex>` ID itself. ADP must correlate the ID returned in each tool response; caller-provided correlation values are never logged or echoed.

HTTP tool-request count and model-call count are separate metrics. Tool logs cannot be used as proof of the model-call budget.

## Stop-loss and cleanup

Stop immediately if secure role credentials, independent evidence traces, model-call records, single-layer End JSON, or the Python gate cannot be demonstrated. Do not compensate by adding UI.

If CloudBase logs show more than one `RIDEREsolve_INSTANCE_START` event during the probe window, or the container restarts after any tool request, invalidate the run, revoke its credentials, and create a new run. The acknowledgement variable does not make the process-local counter durable.

After the probe, revoke the run, remove the role credentials from ADP, remove public traffic from the test service, and retain only redacted audit evidence and the pass/fail report.
