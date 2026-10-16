# ADP workflow-first tool migration

> Superseded for deployment by `ACCURACY_FIRST_DEPLOYMENT.md` and
> `accuracy_first_manifest.json`. This file remains a historical record.

## Decision

All five Agent configurations must have an empty tool list. The ADP workflow owns every HTTP
call, its fixed request body, retry/timeout policy, role credential, and output handoff. Agents
only transform already returned, role-scoped data into structured JSON.

This directly addresses the failures in the first five-Agent run: an Advocate attempted an
unauthorized operation, another emitted tool-call syntax as answer text, and policy retrieval
was retried after an ambiguous request. A fixed graph makes those states observable and keeps
tool failures out of model reasoning.

The machine-readable source of truth is `workflow_first_manifest.json`. The checked-in
`RideResolve-Orchestration-import.zip` remains a legacy three-Agent snapshot and must not be
imported as the workflow-first design.

## Target graph

```text
Start
  -> [Evidence] get_case_snapshot
  -> [Evidence] get_trip_evidence
  -> [Evidence] get_policy_rules
  -> Evidence Collection Agent (no tools)
  -> [Rider] get_trip_evidence
  -> Rider Advocate (no tools)
  -> [Driver] get_trip_evidence
  -> Driver Advocate (no tools)
  -> [Policy] get_policy_rules
  -> [Policy] search_precedents
  -> Policy & Precedent Agent (no tools)
  -> Judge (no tools)
  -> deterministic JSON parse
  -> End
```

The graph deliberately keeps seven explicit calls. Rider and Driver still receive independently
audited evidence responses under separate role credentials, but the model can no longer choose
an unauthorized operation, change request parameters, retry, or skip the call.

## Tool-node request bodies

Use the deployed API tool definition in `api/rideresolve-tools.openapi.json`. Configure the
request body as a fixed value, not a model-produced value.

| Tool nodes | Fixed body |
|---|---|
| `get_case_snapshot` | `{}` |
| every `get_trip_evidence` | `{"evidence_types":["PLATFORM_GPS","ROUTE_BASELINE","FARE_LEDGER","AUTHENTICATED_CHAT","DEMO_TRAFFIC_FEED","TRIP_EVENT_LOG","CONTACT_LOG"],"detail":"SUMMARY"}` |
| every `get_policy_rules` | `{"scope":"APPLICABLE_DISPUTE"}` |
| `search_precedents` | `{"limit":3}` |

The evidence-type union covers Route Deviation and No-Show. The version-pinned server returns
only records present in the authorized case. `PARTY_STATEMENT` and
`HISTORICAL_BEHAVIOR_PROFILE` are intentionally excluded from the adjudication path.

## Credentials and Agent cleanup

Create seven workflow tool nodes using the role-specific APIKey values below. The values stay in
ADP's masked authorization field and must never be mapped to an Agent input or exported output.

| Workflow nodes | Credential role |
|---|---|
| Evidence snapshot/evidence/policy | `EVIDENCE_COLLECTION` |
| Rider evidence | `RIDER_ADVOCATE` |
| Driver evidence | `DRIVER_ADVOCATE` |
| Policy rules/precedents | `POLICY_PRECEDENT` |

Then open every Agent configuration and remove all tools. Confirm the tool count is zero for
Evidence Collection, Rider Advocate, Driver Advocate, Policy & Precedent, and Judge. Do not give
the Judge a role token; it has no workflow call.

## Agent input mapping

Map the complete successful tool-node output (including `request_id` and `result`) into the
named Agent input. Do not ask a model to extract or construct a URL, header, or request body.

| Agent input | ADP source |
|---|---|
| Evidence `case_input` | `SYS.UserQuery` |
| Evidence `case_snapshot_result` | Evidence snapshot tool output |
| Evidence `trip_evidence_result` | Evidence trip tool output |
| Evidence `policy_rules_result` | Evidence policy tool output |
| Rider `case_input` | `SYS.UserQuery` |
| Rider `evidence_package` | Evidence Collection `Output.Content` |
| Rider `advocate_evidence_result` | Rider evidence tool output |
| Driver `case_input` | `SYS.UserQuery` |
| Driver `evidence_package` | Evidence Collection `Output.Content` |
| Driver `advocate_evidence_result` | Driver evidence tool output |
| Policy `case_input` | `SYS.UserQuery` |
| Policy `policy_rules_result` | Policy rules tool output |
| Policy `precedent_search_result` | Precedent tool output |
| Judge inputs | unchanged structured outputs from the preceding four Agents |

Use the launch prompts in `docs/adp/prompts/`. They now explicitly reject tool-call syntax and
fail closed when a supplied result is absent, unsuccessful, role-mismatched, or run-mismatched.

## Failure behavior

- Configure each workflow tool node to interrupt the normal path on HTTP/auth/schema failure.
- Do not let an Agent retry a failed tool node or synthesize a substitute response.
- If the platform requires an exception branch, route it to a fixed technical-failure JSON
  response. Do not label transport/authentication failures as human-review business cases.
- Keep the existing deterministic Python gate authoritative after the ADP End output.

## Acceptance checks

1. All five Agent tool lists are empty.
2. The trace has exactly seven successful workflow tool calls and no tool event nested under an
   Agent thought/action trace.
3. Operation order, role, fixed parameters, request ID, and returned IDs match the manifest and
   Python audit log.
4. Rider and Driver citations are non-empty subsets of their own role-specific tool-node result.
5. Three consecutive Route Deviation runs produce the same status/action/rule and no retries.
6. One No-Show run completes without changing tool parameters.
7. Malformed/missing tool output and malformed Judge JSON fail closed.
8. The Python deterministic gate accepts the final recommendation without repair.

Run the local contract checks before editing the cloud workflow:

```powershell
python -m unittest tests.test_workflow_first_contract -v
```
