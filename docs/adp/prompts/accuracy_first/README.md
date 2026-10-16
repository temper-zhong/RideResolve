# Accuracy-first ADP prompts

These prompts replace the earlier workflow-first and Agent-owned-tool prompt records for the
production-shaped demo workflow. They define one public-facing Coordinator plus five specialist
Agent roles. Status, rule, action, fee item, amount, currency, and official-over-mock precedence
remain controlled by deterministic Python code.

The prompt files are:

- `coordinator.md` - public request routing and validated-result presentation;
- `evidence_collection_agent.md` - locked evidence and policy-scope validation;
- `rider_advocate.md` - evidence-grounded rider argument;
- `driver_advocate.md` - evidence-grounded driver argument;
- `policy_precedent_agent.md` - versioned policy and advisory precedent;
- `judge.md` - authoritative-result preservation and concise explanations.

The Coordinator is the public application shell and is not counted as a sixth adjudication
specialist. The workflow invariant remains exactly five specialist Agents.

Use `docs/adp/accuracy_first_manifest.json` as the workflow source of truth. ADP Agent nodes must
run strictly one after another; this platform configuration does not run Agent nodes in parallel.

Reply-token ceilings:

| Agent | Maximum reply tokens |
|---|---:|
| Evidence Collection | 450 |
| Rider Advocate | 550 |
| Driver Advocate | 550 |
| Policy & Precedent | 450 |
| Judge | 700 |

All evidence tool nodes should request `detail="DECISION_FACTS"`. The Judge Agent has no attached
tools. The workflow calls `resolve_case_context` first with `SYS.UserQuery`, then passes the returned
opaque `run_context` directly between tool nodes. Never put `run_context` into an Agent input or ask
a model to reproduce it. The separate workflow-owned Gate connector calls
`get_deterministic_evaluation` before the Judge and `validate_recommendation` after JSON parsing.

Descriptions without an exact official `DISP-*` or `TRIP-*` reference return
`NEEDS_CLARIFICATION`; the intake layer must not guess a person's case from semantic similarity.

Public synthetic demonstrations may also be referenced by exact `DEMO-*` identifiers. Intake may
map a public `TRIP-*` reference to an internal `DEMO-*` or `DISP-*` case ID; that alias mapping is
authoritative and must not be reported by downstream Agents as a mismatch.

Do not deploy any prompt that embeds `DEMO_POLICY_V1` decision order for an official case. The
locked case snapshot selects its policy version, and official data wins over legacy mock data.
