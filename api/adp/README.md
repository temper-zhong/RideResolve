# ADP OpenAPI versions

Use only the six documents under `api/adp/v0_6/` for the current deployment:

1. `rideresolve-intake-tools.openapi.json`
2. `rideresolve-evidence-tools.openapi.json`
3. `rideresolve-rider-tools.openapi.json`
4. `rideresolve-driver-tools.openapi.json`
5. `rideresolve-policy-tools.openapi.json`
6. `rideresolve-gate-tools.openapi.json`

The five role documents directly under `api/adp/` are retained only for v0.5 compatibility tests. They do not include natural-language Intake and must not be imported as the current application.

The public v0.6 input is `SYS.UserQuery`. Intake resolves an explicit official `DISP-*` or `TRIP-*` reference and creates `run_id` internally. The user does not provide `run_id`.
