# ADP orchestration record

RideResolve currently uses Tencent Cloud ADP for the model-facing orchestration layer and Python for the deterministic trust boundary.

## Target workflow shape

```text
Start
  -> parallel role-scoped prefetch + deterministic evaluation
  -> Evidence Collection Agent (no tools)
  -> Rider Advocate / Driver Advocate / Policy & Precedent Agent in parallel
  -> Judge explanations (no tools)
  -> deterministic JSON parse node
  -> server-side validate_recommendation
  -> concise Reply + validated End
```

The workflow keeps five tool-free Agents. Tool prefetch and the three analysis branches run in
parallel. A workflow-owned deterministic tool supplies the locked policy result before Judge,
and a second workflow-owned tool rejects any conflicting Judge output after JSON parsing. The
two Gate operations use the Judge run credential but are never attached to the Judge Agent.

The exported ADP ZIP stored at the repository root as `RideResolve-Orchestration-import.zip` is
a legacy three-Agent snapshot. Cloud-side Agent and tool-node IDs are not fully portable in that
archive. Do not use it for the accuracy-first migration. The deployment source of truth is
`accuracy_first_manifest.json`, the exact setup is in `ACCURACY_FIRST_DEPLOYMENT.md`, and the
Agent prompt contracts are under `prompts/accuracy_first/`.

## Stretch-goal path

The target demo keeps a bounded **Evidence Collection Agent** before the two Advocates. Fixed
workflow nodes retrieve the role-isolated case/evidence/policy records; the Agent validates and
packages those returned records plus explicit gaps. It cannot call tools or decide liability,
status, action, or money.

The prompt contract is preserved in `docs/adp/prompts/evidence_collection_agent.md`. Its 2026-10-12 ADP execution was live, while the records it queried were explicitly synthetic. `LIVE` execution and `SYNTHETIC` data provenance are separate labels.

The local demo also implements a fifth **Policy & Precedent Agent** together with a **Learning
Feedback Loop**. A genuine human override must include evidence citations, a correction reason,
a changed outcome, advisory-only approval, and a valid checksum before it enters the append-only
precedent memory. Workflow nodes retrieve current policy and matching reviewer-approved
precedents; the Agent validates them and supplies cited `ADVISORY_ONLY` context to the Judge. It
cannot call tools, copy a historical outcome, modify policy, or change the deterministic result.

The Policy & Precedent prompt contract is preserved in `docs/adp/prompts/policy_precedent_agent.md`. Its ADP node and role-scoped precedent-search binding were exercised live on 2026-10-12 against the synthetic precedent fixture.

The third implemented stretch capability is the deterministic **Escalation Protocol**. A blocked evidence gate or a Judge self-confidence score below `70/100` creates a complete human-review packet. Low model confidence can only escalate a case; high confidence can never bypass the evidence and policy gates.

The logical five-Agent dependency graph is:

```text
Evidence Collection Agent
  -> Rider Advocate / Driver Advocate / Policy & Precedent Agent
  -> Judge
  -> deterministic Python validation
  -> Escalation Protocol when required
```

## Tool isolation

| Agent | Attached tools | Workflow-owned input |
|---|---|---|
| Evidence Collection Agent | None | Evidence-role snapshot, evidence, and policy nodes |
| Rider Advocate | None | Rider-role evidence node |
| Driver Advocate | None | Driver-role evidence node |
| Policy & Precedent Agent | None | Policy-role rules and precedent nodes |
| Judge | None | Supplied Agent outputs plus authoritative deterministic evaluation |

The separate Gate connector is workflow-owned, not Agent-owned.

Each tool node uses only the bounded read-only operations authorized for its role. API keys are
stored on workflow nodes, never in prompts or Agent inputs. Money and final status remain behind
the deterministic Python gate.

## Execution truth labels

- `LIVE`: an active ADP execution observed during the demonstration.
- `REPLAY`: a stored, complete output from a prior real ADP execution.
- `SYNTHETIC`: fixture evidence or generated offline Agent text.

The current Streamlit page uses `SYNTHETIC`. The 2026-10-12 ADP Route Deviation execution is a `LIVE` execution over `SYNTHETIC` data; it must not be described as production ride-hailing evidence. A stored run may be labelled `REPLAY` only when its complete exported artifact is retained.

## Deterministic boundary

ADP recommendations are not final decisions. Python independently validates:

- evidence membership, provenance, checksum, and input fingerprint;
- policy version and effective period;
- evidence completeness and conflicts;
- allowed action type, fee item, currency, and ledger-derived amount;
- exact agreement between Judge recommendation and program-allowed status/action.

Any model integrity failure is a technical failure, not a difficult business case disguised as human review.

## Semantic and historical context boundary

The Advocate contract now supports structured chat annotations for sentiment, consent, disagreement, and threat. The offline page displays only clearly labelled synthetic annotations; a real ADP output must keep its original evidence citation before it can be labelled `LIVE` or `REPLAY`.

Synthetic historical behavior profiles are also exposed as `SUPPORTING` evidence to cover account age, rating pattern, and prior-dispute context. They are intentionally excluded from policy evaluation, credibility, liability, final status, and money. Tests verify that removing the profile leaves the matched rule and action unchanged.
