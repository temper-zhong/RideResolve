# Official dataset integration

RideResolve imports the four hackathon-provided Markdown files into immutable local source
archives, normalized case/evidence fixtures, and a versioned executable policy. The import is
reproducible with `scripts/import_official_datasets.py`; `data/official_sources/source_manifest.json`
records SHA-256 hashes for all four source files.

## Precedence and compatibility

- Official sample values and expected outcomes take precedence over conflicting legacy mock
  assumptions for `DISP-001`, `DISP-002`, and `DISP-003`.
- Official cases are pinned to `RYDE_POLICY_V2_1`; legacy mock cases remain pinned to
  `DEMO_POLICY_V1`. This preserves the existing Decision Delta demo while preventing old mock
  thresholds from being applied to official cases.
- Where the official route sample's explicit expected outcome conflicts with the generic
  automation eligibility text, the case-specific official ground truth is used: `DISP-001`
  resolves to a SGD 3.44 partial refund. The result remains a simulated prototype ruling.
- Historical examples supplied in policy section 7 are exposed as `ADVISORY_ONLY` precedents
  and cannot override current policy or determine an outcome by themselves.

## Normalized official cases

| Case | Type | Deterministic rule | Expected action |
|---|---|---|---|
| `DISP-001` | Route deviation | `RD-104` | Partial refund of SGD 3.44 excess-distance fare |
| `DISP-002` | No-show | `NS-102` | Uphold the fixed SGD 5.00 cancellation charge |
| `DISP-003` | Fare dispute | `FD-103` | Refund the SGD 4.50 unnotified surge differential |

The v2.1 evaluator also encodes the material counterfactuals: route notification suppresses the
route refund, missing either required no-show contact channel voids the charge, and a verified
surge notification suppresses the fare-difference refund.
