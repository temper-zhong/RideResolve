# RideResolve v0.6 local handoff

Date: 2026-10-16 (Asia/Singapore)

## Completed locally

- Deterministic official-case intake from `SYS.UserQuery`.
- Exact `DISP-*` and `TRIP-*` reference resolution; description-only input fails closed with
  `NEEDS_CLARIFICATION`.
- Server-created internal runs with 300 requests per role.
- HMAC-signed run context bound to run, case version, policy version, and expiry.
- Expiry-bounded static intake and five-role ADP connector credentials through
  2026-11-04 23:59:59 Asia/Singapore.
- Six v0.6 ADP OpenAPI files: intake plus Evidence, Rider, Driver, Policy, and Gate.
- Strictly serial five-Agent workflow manifest with one End node and converged clarification and
  technical-failure branches.
- Judge prompt guard requiring an integer confidence score from 0 through 100.
- WorkBuddy MCP server with text/file tools and official ADP Chat API SSE handling.
- Fixed signed-session expiry matching so production timestamps with microseconds are compared at
  the authenticated NumericDate whole-second precision instead of being rejected as HTTP 401.
- Sanitized v0.5 successful End result archived under `docs/evidence/accuracy_first_v0_5/`.
- Complete local test suite: 137 pytest tests and 133 unittest tests passed; compilation and `pip check` also passed.

## Packages

| Artifact | SHA-256 |
|---|---|
| `dist/rideresolve-cloudbase-v0.6.0-session-intake-context-fix.zip` | `ACFD662B0B7AAE245B94BB8CE242C13DEA0FE35FFDF67584E161F13A4D73FFB4` |
| `dist/rideresolve-workbuddy-mcp-v0.6.0.zip` | `F3D654DA82131E272D3677252D86572E5EC0D9B85C5C64AEA5A2358C9241A3B3` |

The fixed CloudBase package contains 36 entries and no `var/` directory. Do not redeploy the older
`rideresolve-cloudbase-v0.6.0-session-intake.zip`, which predates the run-context fix. A scan of all source,
documentation, OpenAPI, integration, script, and test files found zero copies of the eight newly
generated secret values outside ignored local `var/` storage.

## Requires console access

1. Deploy the v0.6 CloudBase package and add the two session environment values.
2. Import the six v0.6 OpenAPI files with their matching local connector secrets.
3. Rebuild the ADP graph from the serial v0.6 manifest and run all acceptance tests.
4. Publish the ADP application and obtain its AppKey.
5. Populate WorkBuddy's MCP configuration with that AppKey, restart WorkBuddy, and run a real
   `adp_chat` smoke test.

No local result is represented as proof that these five external actions have occurred.

## Submission package status

- `dist/RR-submit-ready.zip` is obsolete and must not be uploaded.
- `dist/RR-submit-candidate-v0.6.0-context-fix.zip` is the current privacy-scanned inspection
  candidate, not a final submission; the candidate without `context-fix` predates the HTTP 401 fix.
- Final-package generation is blocked until the required CodeBuddy/WorkBuddy evidence is manually reviewed and hash-recorded under `docs/process_records/submission/`.
