# RideResolve v0.6 accuracy-first ADP deployment

## Release boundary

This release accepts an external natural-language request from `SYS.UserQuery`. It does not ask
the user for an internal `run_id`. The intake tool resolves an explicit official `DISP-*` or
`TRIP-*` reference, creates the internal run, and returns an opaque signed `run_context` for the
remaining workflow tool nodes.

The resolver deliberately does not select a person's case from semantic similarity alone. A
description without an exact official reference returns `NEEDS_CLARIFICATION`. Official dataset
values and the case-pinned official policy override conflicting legacy mock values.

## Security model

- The intake connector and the five role connectors each use a different static secret.
- Static connector secrets expire at `2026-11-04T23:59:59+08:00` in the generated local bundle.
- Raw values exist only under `var/session_v0_6/` and must not be committed or pasted into prompts.
- `run_context` is HMAC-signed, short-lived, and bound to run, case, case version, policy version,
  and expiry. The server-side registry remains authoritative for status and the 300-request budget.
- Pass `run_context` directly from the intake output to tool request bodies. Do not expose it to an
  Agent node or ask a model to generate, summarize, or modify it.
- CloudBase must remain fixed to one minimum and one maximum instance because the current probe
  registry is local to the container instance.

## CloudBase update

Deploy the new v0.6 package, keeping the existing registry variables, then add both values from
`var/session_v0_6/cloudbase-session-environment.json`:

- `RIDERESOLVE_CONNECTOR_CREDENTIALS_B64`
- `RIDERESOLVE_CONTEXT_SIGNING_KEY_B64`

Do not print those values in deployment logs. After deployment, verify `/health`, then test the
intake endpoint and one role endpoint before changing the ADP workflow.

## ADP OpenAPI imports

Import all six files from `api/adp/v0_6/` as new connector definitions:

1. `rideresolve-intake-tools.openapi.json`
2. `rideresolve-evidence-tools.openapi.json`
3. `rideresolve-rider-tools.openapi.json`
4. `rideresolve-driver-tools.openapi.json`
5. `rideresolve-policy-tools.openapi.json`
6. `rideresolve-gate-tools.openapi.json`

Configure header authentication as follows:

| Connector | Header | Local secret source |
|---|---|---|
| Intake | `X-RideResolve-Intake-Token` | `intake` |
| Evidence | `X-RideResolve-Run-Token` | `roles.EVIDENCE_COLLECTION` |
| Rider | `X-RideResolve-Run-Token` | `roles.RIDER_ADVOCATE` |
| Driver | `X-RideResolve-Run-Token` | `roles.DRIVER_ADVOCATE` |
| Policy | `X-RideResolve-Run-Token` | `roles.POLICY_PRECEDENT` |
| Gate | `X-RideResolve-Run-Token` | `roles.JUDGE` |

The Gate connector belongs only to workflow-owned tool nodes. Do not attach it to the Judge Agent.

## Required serial graph

ADP Agent nodes must not be configured to run in parallel. Build this exact main chain:

```text
Start (SYS.UserQuery)
  -> resolve_case_context
  -> condition: MATCHED and run_created
  -> get_case_snapshot
  -> Evidence get_trip_evidence
  -> Evidence get_policy_rules
  -> Evidence Collection Agent
  -> Rider get_trip_evidence
  -> Rider Advocate Agent
  -> Driver get_trip_evidence
  -> Driver Advocate Agent
  -> Policy get_policy_rules
  -> search_precedents
  -> Policy & Precedent Agent
  -> get_deterministic_evaluation
  -> Judge Agent
  -> parse_judge_json
  -> serialize_judge_recommendation
  -> validate_recommendation
  -> Set Success Result
  -> Reply
  -> End
```

There must be exactly one End node. The clarification and technical-failure branches both converge
on that same End node through `WF.final_result`.

## Node mappings

`resolve_case_context`:

```json
{
  "user_query": "<SYS.UserQuery>"
}
```

The v0.6 ADP Intake connector intentionally exposes only `user_query`. Reference extraction is
performed deterministically by `resolve_case_context`; there is no separate model-based Intake
Extractor node. The underlying service can accept explicit reference fields for non-ADP clients,
but they are omitted from the ADP OpenAPI document to prevent the platform from serializing
unchecked optional fields as empty strings and causing HTTP 422 validation failures.

Every later tool request includes:

```json
{
  "run_context": "<resolve_case_context.Output.result.run_context>"
}
```

Add the existing operation-specific values beside it. All evidence calls use
`detail="DECISION_FACTS"`; policy calls use `scope="APPLICABLE_DISPUTE"`; precedent search uses
`limit=3`; deterministic evaluation uses `scope="LOCKED_RUN"`.

The Judge receives the internal `run_id`, deterministic evaluation, evidence package, two Advocate
arguments, and precedent advisory. It receives neither a connector secret nor `run_context`.

`validate_recommendation`:

```json
{
  "run_context": "<resolve_case_context.Output.result.run_context>",
  "run_id": "<parse_judge_json.Output.run_id>",
  "recommendation": "<serialize_judge_recommendation.Output.recommendation_json>"
}
```

Add `serialize_judge_recommendation` as a Python Code node after `parse_judge_json`. Its input
is `recommendation` from `parse_judge_json.Output.recommendation` (type `object`); declare an
output property named `recommendation_json` with type `string`, and use:

```python
import json

def main(params: dict) -> dict:
  return {
        "recommendation_json": json.dumps(
            params["recommendation"], ensure_ascii=False, separators=(",", ":")
        )
  }
  ```

The Gate accepts this string and, for ADP client compatibility, also safely unwraps
one additional JSON-string transport layer before performing the same strict
recommendation validation. This is a **CloudBase service** change only; the
`serialize_judge_recommendation` node and its existing mapping stay unchanged.

ADP cannot reliably transport a nested object containing JSON `null` into a custom API node. The
Gate connector therefore carries this one field as JSON text. The deployed Gate parses it once and
then validates the complete object against the same strict `JudgeRecommendation` contract.

## Branches and the single End

When intake is not `MATCHED`, assign:

```json
{
  "status": "NEEDS_CLARIFICATION",
  "validated": false,
  "message": "<resolve_case_context.Output.result.message>"
}
```

Every node's exception edge must assign:

```json
{
  "status": "TECHNICAL_FAILURE",
  "validated": false,
  "message": "The workflow stopped before a validated decision was produced."
}
```

The technical-failure Reply text is:

```text
Technical failure: the workflow stopped before a validated decision was produced. No refund, fee adjustment, notification, or final case decision was executed.
```

The single End node returns:

```json
{
  "result": "<WF.final_result>"
}
```

## Acceptance tests

Run these in order after importing the v0.6 connectors:

1. `Please review case DISP-001. The driver took a longer route and I was charged extra.`
   Expected authoritative result: `RD-104`, partial refund recommendation, SGD 3.44.
2. `Please review trip TRIP-2026-09945. I was charged a no-show fee.`
   Expected authoritative result: `NS-102`, `NO_ACTION`, SGD 0.00.
3. `The final fare was higher than the quote.`
   Expected: `NEEDS_CLARIFICATION`; no run-dependent Agent or Gate node executes.
4. Change a successful Judge action or amount before validation.
   Expected: HTTP 409 and `TECHNICAL_FAILURE`, never `PENDING_HUMAN_REVIEW`.
5. Confirm final success output includes `validation_status="PASSED"` and
   `validated_by="PYTHON_DETERMINISTIC_GATE"`.

Only publish the ADP application after all five tests pass. Publishing creates the AppKey used by
the WorkBuddy connector; the AppKey is unrelated to the six ADP OpenAPI connector secrets.
