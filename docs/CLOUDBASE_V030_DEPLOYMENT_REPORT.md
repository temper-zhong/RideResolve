# CloudBase v0.3.0 deployment report

Deployment date: **2026-10-11**

## Result

The five-role read-only tool backend is deployed to the existing controlled CloudBase Run service.

| Field | Verified value |
|---|---|
| Environment | `rideresolve-probe-d9dax69bbd0c97` |
| Service | `rideresolve-gate-a-probe` |
| Online version | `rideresolve-gate-a-probe-006` |
| Traffic | `100%` |
| Service status | `normal` |
| Instance limits | minimum `1`, maximum `1` |
| Container port | `8080` |
| HTTPS origin | `https://rideresolve-gate-a-probe-325140-12-1501522460.sh.run.tcloudbase.com` |
| OpenAPI version | `0.3.0` |
| Configuration task | `2331146`, `finished` |

The source deployment artifact is `dist/rideresolve-cloudbase-v0.3.0.zip` with SHA-256:

```text
C79E36AAC0A3649284B513A50C8869D45784A1CB5DA7F9A7B89E40BE6D45ED20
```

The package contained 25 files and no `.env`, `var`, `docs`, `tests`, `.git`, `__pycache__`, raw connector credential, obvious API key, or embedded run-registry value.

## Deployed capability checks

The public health endpoint returned `status=ok` and `synthetic=true`. The public OpenAPI endpoint returned version `0.3.0` and all four operations:

- `get_case_snapshot`
- `get_trip_evidence`
- `get_policy_rules`
- `search_precedents`

One short-lived five-role run was issued for the synthetic `CASE-RD-001 v2` fixture:

```text
RUN-524cf4c74f864a3e9d1a74aa68abca2f
```

Only the hashed single-run registry was placed in CloudBase. Raw tokens remain in the ignored local `var/` directory and expire at `2026-10-14T06:32:40.785360+00:00`.

The post-deployment HTTPS smoke test verified:

- the Evidence Collection credential could call snapshot, evidence, and policy operations;
- `HISTORICAL_BEHAVIOR_PROFILE` was returned through the deployed schema and evidence endpoint;
- the Policy & Precedent credential retrieved `FB-RD-004-001` with `authority=ADVISORY_ONLY`;
- a Rider credential calling `search_precedents` received HTTP `403`;
- a Policy & Precedent credential calling raw trip evidence received HTTP `403`.

## Claim boundary

This proves that the five-role credential layer, the fourth-Agent evidence tools, and the fifth-Agent precedent tool are deployed and role-isolated on CloudBase. It does **not** prove that the Evidence Collection Agent or Policy & Precedent Agent has run as an ADP model node. The preserved real ADP evidence still covers only Rider Advocate, Driver Advocate, and Judge.

Do not publish the local credential file, hashed registry file, or CloudBase environment-variable values. Revoke or replace the deployed run after the ADP verification window.
