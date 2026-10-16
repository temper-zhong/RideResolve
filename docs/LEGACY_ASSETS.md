# Legacy assets

`RideResolve-Orchestration-import.zip` is a historical three-Agent ADP snapshot created before the v0.6 Intake and session design. It is retained locally for forensic comparison only.

Do not import, upload, or describe it as the current application. The canonical v0.6 deployment inputs are:

- `docs/adp/accuracy_first_manifest.json`
- `api/adp/v0_6/rideresolve-intake-tools.openapi.json`
- the five role-specific OpenAPI files in `api/adp/v0_6/`

The public entry point is a natural-language `SYS.UserQuery`. `run_id` is generated internally after Intake resolves a unique explicit official `DISP-*` or `TRIP-*` reference.
