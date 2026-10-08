# RideResolve

Evidence-grounded three-agent ride-hailing dispute-resolution prototype.

Current scope:

- immutable case snapshots and reusable raw evidence;
- deterministic GPS merging, coverage, and distance calculation;
- explicit Route Deviation and No-Show policy evaluators;
- ledger-derived refund limits;
- Judge recommendation consistency checks;
- minimal Decision Delta comparison.
- read-only, short-lived role-token-protected case, evidence, and policy tools for the approved ADP Gate A probe.

Gate A is not yet complete because the read-only tool service is currently local and has not yet been exposed through public HTTPS and imported into ADP. Never commit API keys or ADP AppKeys.

The ADP workflow orchestration smoke test has passed with Rider Advocate, Driver Advocate, and Judge. Gate A still requires a real ADP run in which the advocates autonomously call the deployed tools; direct injection of all evidence into the user prompt does not count.

Run the current tests with the bundled Python runtime from this directory:

```powershell
python -m unittest discover -s tests -v
```

## Local Gate A probe tool API

Create a short-lived synthetic run. Raw role tokens are written only under ignored `var/probe_credentials`; the registry stores hashes:

```powershell
python scripts/create_probe_run.py --case-id CASE-RD-TOOL-001 --case-version 1
python -m rideresolve.tool_api --host 127.0.0.1 --port 8000
```

Available routes:

- `GET /health`
- `GET /openapi.json`
- `POST /tools/get_case_snapshot`
- `POST /tools/get_trip_evidence`
- `POST /tools/get_policy_rules`

Example:

```powershell
# Read one role token locally from the generated credential file.
# Never paste it into prompts, chat, screenshots, or committed files.
$headers = @{'Content-Type'='application/json'; 'X-RideResolve-Run-Token'='<local role token>'}
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8000/tools/get_case_snapshot' -Headers $headers -Body '{}'
```

The ADP import template is at `api/rideresolve-tools.openapi.json`. Generate a new fixed document with the actual HTTPS origin before import:

```powershell
python scripts/build_openapi.py --server-url https://ACTUAL_CONTROLLED_HOST
```

For the probe, import/configure one role-specific copy per Agent so Rider, Driver, and Judge use different short-lived credentials. The current experiment is not approval to adopt the hybrid architecture as the formal baseline.
