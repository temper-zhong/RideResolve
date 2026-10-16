# Two-minute RideResolve walkthrough

## Truth label before speaking

The current local page is `SYNTHETIC`. Do not call it a replay. Use `REPLAY` only after complete model-run artifacts for that exact case version are stored and verified.

## 0-20 seconds - Refuse to guess

Open `Decision Delta - Route Deviation`, version `v1 - incomplete GPS`.

Say:

> RideResolve has five specialist Agents: Evidence Collection, Rider Advocate, Driver Advocate, Policy and Precedent, and Judge. The model never controls money or final status. In version one, GPS covers only 70% of the trip, so RD-001 requests human review instead of guessing.

Point to:

- `SYNTHETIC - OFFLINE DEMO`;
- GPS coverage `70/100`;
- `BLOCKED AS DESIGNED`;
- `Pending human review`.

Briefly show the collection and escalation panels:

> The Evidence Collection Agent detects the missing GPS coverage before either side argues. The Escalation Protocol creates a complete review packet. Low Judge confidence may trigger a handoff, but it can never approve a case.

## 20-50 seconds - Show independent cases

Scroll to the two Advocate columns.

Say:

> Rider and Driver inspect the same immutable package but select evidence for their own positions. Every claim is tied to a visible evidence ID. The Judge recommends an outcome, while Python validates the cited evidence, policy version, action, and ledger amount.

Open one evidence provenance expander. Emphasize that text inside evidence is treated as data, not instructions.

Briefly point to Conversation semantics and Historical context:

> The model can organize chat into sentiment, consent, disagreement, and threat signals, but those are interpretations, not facts. Historical patterns are context only. Neither can decide credibility, liability, status, or money.

## 50-75 seconds - Add exactly one trusted record

Switch to `v2 - GPS supplemented`.

Say:

> Version two reuses every version-one record and adds exactly one authoritative GPS supplement. Its checksum, origin case, supplement role, and links to the prior GPS segments are verified before evaluation.

Point to `EV-RD-GPS-SUPPLEMENT` and its `related_evidence_ids`.

## 75-105 seconds - Show the deterministic result

Point to the hard gates and final status.

Say:

> Coverage is now 100%. RD-001 no longer blocks the case. The Policy and Precedent Agent retrieves two reviewer-approved RD-004 corrections involving late or corrected evidence. It tells the Judge to check those conditions, but it does not copy either historical outcome. The current ledger and route baseline have no conflict, so RD-004 still permits only SGD 3.25. The escalation trigger clears. This is a simulated resolution; no real refund or notification was executed.

## 105-120 seconds - Land the differentiator

Open the Decision Delta table.

Say:

> Decision Delta does not merely show that an AI changed its answer. It verifies the exact chain: one evidence record changed one fact, which changed the matched rule, allowed action, and simulated money, while every other business input stayed fixed.

End with:

> Five Agents organize evidence, both parties, policy, and precedent. Python owns evidence integrity, policy, feedback publication, amount, escalation, and final status. The model can recommend; it cannot overrule the gates.

## After the two-minute path

- Switch to `No-Show - Valid Charge` to prove the second dispute category exists.
- Show that the collector automatically selects the No-Show evidence-source plan.
- If platform access is stable, show the preserved Route Deviation ADP workflow outside the two-minute main path.
- Describe the recorded ADP execution as a functional three-core-agent run. The optional Evidence Collection and Policy & Precedent Agents are locally tested but not yet live in ADP.
