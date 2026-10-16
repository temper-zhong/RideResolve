# Gate A functional run evidence report

Status: **Functional ADP workflow demonstrated; formal Gate A artifact sign-off pending.**

This report records exactly what the preserved local evidence proves about the historical Route Deviation run and the newer workflow-first No-Show run. Neither run must be presented as a formal Gate A pass.

## Preserved evidence

| Artifact | SHA-256 | What is visible |
|---|---|---|
| `docs/evidence/adp-route-deviation-functional-run.png` | `538A505DDA7AD21343BE11DF86896A5F749AB5243D716965B4DAB9D6D44DB6D4` | A successful ADP workflow containing Rider Advocate, Driver Advocate, Judge, JSON reply, and End nodes; the debug panel shows a structured Judge result. |
| `docs/evidence/adp-tool-configuration.png` | `75317F7F9A51B8BC906BAB5FA94E89BFB320E9FEC9CA8AEEBF4E96FDB9F9ED68` | The Rider tool configuration contains the three bounded operations: `get_case_snapshot`, `get_trip_evidence`, and `get_policy_rules`. |
| `docs/evidence/workflow_first_no_show/ns_adp.png` | `9453EE23CC57CB7CAA96D950169AFA43199239677AB4C0FD736F2FB228A85782` | All 15 No-Show workflow steps are green, including five Agent nodes, seven explicit tool nodes, the deterministic gate, and End. |
| `docs/evidence/workflow_first_no_show/ns_audit.png` | `6271DD4EA0A33726A7FCF51C8098D18EAF7842AA7CC971B2B84F02ADCD961487` | CloudBase log results filtered to the same non-secret No-Show run ID. |
| `docs/evidence/workflow_first_no_show/end.json` | `E00A99592F8AB34E250FDF7EEFA714EC4C4F992873DE17787B4F57B97F6B7F85` | Structured No-Show End result: `RESOLVED / NS-002 / NO_ACTION / 0 SGD`. |
| `docs/evidence/ns_run/ns_audit_report.json` | `7A86BDABDD420844E2A4212FDEFD64A6D4B6DA13C6CDBA5BE3FE942A5B324071` | Sanitized seven-event audit summary with one run, case, policy, and server instance. |

The original Word process record contains the same two PNG files byte-for-byte. Four separately downloaded `rideresolve-gate-a-probe-*-log.txt` files were also inspected. They are CloudBase image build and push logs, not model-run request audit exports, so they are not counted as Gate A execution evidence.

## Historical Route Deviation findings

- The three named ADP Agent nodes completed successfully in one visible workflow.
- The workflow passed through a JSON reply node and an End node.
- The visible final result is a structured Route Deviation recommendation with:
  - `recommended_case_status = RESOLVED`;
  - `recommended_action.type = REFUND_DISPUTED_FEE_FULL`;
  - `fee_item = distance_surcharge`;
  - `amount_cents = 325` and `currency = SGD`;
  - policy citations including `RD-004`;
  - separate rider and driver explanations.
- The ADP interface screenshot displays `22.6s`, while a separate development transcript described a longer end-to-end elapsed time. Because no original exported timestamp trace was preserved, this report makes no authoritative latency claim from either value.

These points support the narrow statement: **a real ADP three-role workflow produced a structured Route Deviation recommendation.**

## Workflow-first No-Show findings

- All five Agent nodes completed with no Agent-owned tools.
- Seven explicit, role-scoped workflow tool nodes completed in the expected order.
- The deterministic gate and End node completed successfully.
- The preserved End result cites `EV-NS-GPS`, `EV-NS-EVENT`, `EV-NS-CONTACT`, and `NS-002`, and recommends `RESOLVED / NO_ACTION / 0 SGD`.
- The sanitized CloudBase report records exactly seven successful HTTP 200 events, unique request IDs, one run identity, one case identity, one policy version, and one server instance.
- The ADP execution panel reported 79.774 seconds. This value is descriptive for the captured run and is not a production latency claim.

These points support the narrow statement: **a functional five-Agent, workflow-first ADP No-Show run produced the expected structured result with matching server-side tool activity.**

## Missing evidence for formal Gate A

The historical Route Deviation run still lacks the complete original artifacts described above. For the newer No-Show run, the repository still lacks:

1. a complete, untruncated original ADP exported trace with platform request and trace IDs;
2. separately preserved structured Rider and Driver final arguments that can be checked against evidence IDs returned to each role;
3. a provenance review binding a future native ADP export hash to the platform trace ID.

The End JSON and matching seven-event CloudBase audit were preserved for No-Show, but the missing native trace and Advocate outputs prevent `verify_probe_artifacts()` from completing formal cross-system acceptance. Reconstructing any missing trace from screenshots or chat text is prohibited.

## Gate decision

| Scope | Decision |
|---|---|
| Historical Route Deviation workflow | Functional demonstration passed |
| Workflow-first No-Show workflow | Functional demonstration passed |
| Deterministic No-Show result | Accepted as `NS-002 / NO_ACTION / 0 SGD` |
| CloudBase tool audit | Seven expected successful events preserved and summarized |
| Native ADP trace correlation | Pending; native trace export unavailable |
| Formal Gate A | Pending |

Permitted submission wording:

> We completed a functional five-Agent, workflow-first ADP No-Show run with a structured End result, deterministic validation, and seven matching CloudBase audit events. Formal cross-system Gate A sign-off remains pending because the complete native ADP trace export and separate Advocate outputs were unavailable.

## Remaining capture for formal sign-off

Before closing the ADP debug page, preserve the following without copying any role token:

1. the full ADP trace export;
2. Rider and Driver structured final outputs;
3. the export file hash and platform trace ID review record.

Only after the strict artifact verifier passes may the Streamlit records be relabelled from `SYNTHETIC` to `REPLAY`.
