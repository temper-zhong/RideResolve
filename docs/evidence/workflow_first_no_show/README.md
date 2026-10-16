# Workflow-first No-Show ADP evidence

Status: **Functional five-Agent cloud workflow demonstrated; formal Gate A artifact sign-off pending.**

This directory contains submission-safe evidence for the No-Show run executed on 2026-10-13. All five ADP Agents had empty tool lists. Seven explicit, role-scoped workflow tool nodes completed before the deterministic gate and End node.

## Artifacts

| File | SHA-256 | Purpose |
|---|---|---|
| `ns_adp.png` | `9453EE23CC57CB7CAA96D950169AFA43199239677AB4C0FD736F2FB228A85782` | ADP canvas showing the 15-step workflow completed successfully. |
| `ns_audit.png` | `6271DD4EA0A33726A7FCF51C8098D18EAF7842AA7CC971B2B84F02ADCD961487` | CloudBase log view filtered to the same non-secret run ID. |
| `end.json` | `E00A99592F8AB34E250FDF7EEFA714EC4C4F992873DE17787B4F57B97F6B7F85` | Structured End result for the same run. |

The End result is `RESOLVED / NS-002 / NO_ACTION / 0 SGD`. The sanitized audit report in `../ns_run/ns_audit_report.json` records seven successful HTTP 200 tool events, one run identity, one case identity, one policy version, unique request IDs, the expected call sequence, and one server instance.

## Boundary

These artifacts prove a successful functional workflow and matching server-side audit activity. They do not constitute formal Gate A sign-off because a complete native ADP trace export and the separately preserved Rider/Driver Agent outputs are unavailable. The run must not be relabelled as `REPLAY`.

No role token, API key, environment registry, or deployment credential is included in this directory.
