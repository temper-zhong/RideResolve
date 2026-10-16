# CloudBase v0.4.0 deployment report

Deployment verification date: **2026-10-14**

## Result

The official hackathon sample datasets and the executable `RYDE_POLICY_V2_1`
policy are deployed to the existing RideResolve CloudBase service.

| Field | Verified value |
|---|---|
| Service | `rideresolve-gate-a-probe` |
| HTTPS origin | `https://rideresolve-gate-a-probe-325140-12-1501522460.sh.run.tcloudbase.com` |
| Health status | `ok` |
| Dataset ID | `RIDERESOLVE_MERGED_MOCK_AND_OFFICIAL_SAMPLES_V1` |
| OpenAPI version | `0.4.0` |
| Public tool paths | `4` |
| Unauthenticated tool request | HTTP `401` |
| Verified server instance | `INSTANCE-470f1df3702741eca6b7b09a4ba49dcd` |

The deployed source artifact is
`dist/rideresolve-cloudbase-v0.4.0-cloudbase-fixed.zip` with SHA-256:

```text
B72702323BD17C0ADDBC5AF4894351C73F6FD1C349BA8AD07591F038D76D976F
```

The fixed artifact contains 27 runtime files. Every ZIP entry uses a portable
ASCII name, forward-slash path, and Unix file metadata. It excludes the raw
official Markdown source filenames because those names caused the first
CloudBase build attempt to fail during Linux extraction. Normalized official
case and policy JSON files remain included.

## Verification

- `95` local tests passed after the package fix.
- A clean extraction of the exact deployed ZIP reproduced all three official
  expected decisions:
  - `DISP-001`: `RD-104`, partial refund of `344` cents.
  - `DISP-002`: `NS-102`, `NO_ACTION`.
  - `DISP-003`: `FD-103`, full refund of `450` cents.
- The live health endpoint reports the merged mock-and-official dataset.
- The live OpenAPI document reports version `0.4.0` and contains
  `SURGE_PRICING_LOG`, `NOTIFICATION_LOG`, policy precedents, and the v2.1 rule
  parameters.
- All four public tool operations are present, while an unauthenticated tool
  call is rejected with HTTP `401`.

## Claim boundary

The official files are hackathon sample data, not production ride records, so
the service correctly continues to report `synthetic=true`. The online checks
prove that the new dataset and interface contract are deployed. The three
official decisions were verified deterministically against a clean extraction
of the exact deployed artifact; no new role credential or production action
was created for this deployment check.
