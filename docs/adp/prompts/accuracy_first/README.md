# Accuracy-first ADP prompts

These prompts replace the earlier workflow-first and Agent-owned-tool prompt records for the
production-shaped demo workflow. They keep all five Agent roles, but move status, rule, action,
fee item, amount, currency, and official-over-mock precedence to deterministic Python code.

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

Do not deploy any prompt that embeds `DEMO_POLICY_V1` decision order for an official case. The
locked case snapshot selects its policy version, and official data wins over legacy mock data.
