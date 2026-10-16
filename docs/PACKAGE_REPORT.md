# Submission package report

Prepared: 2026-10-16

Candidate archive: `dist/RR-submit-candidate-v0.6.0-context-fix.zip`

Status: **inspection candidate only; do not upload as the final submission**

SHA-256: `23FCE197693A5DCE7AFE1BCE080527A7EC2AD795CD16AD1E59DD5E1EDF1707E8`

## Canonical architecture

The package declares one public entry path:

`SYS.UserQuery -> official Intake -> signed internal run context -> five strictly serial tool-free Agents -> deterministic Gate -> one End`

The user supplies a normal problem description containing an explicit official `DISP-*` or `TRIP-*` reference. The system creates `run_id` internally. Official data overrides conflicting legacy mock data.

`docs/adp/multiagent_manifest.json` is included only as an explicitly marked, unvalidated historical experiment. It is not the submitted architecture.

## Included

- current v0.6 source, official/synthetic datasets, tests, and reproducibility lock file;
- the signed-session expiry precision fix that prevents valid Intake contexts with microseconds
  from being rejected by downstream tools as HTTP 401;
- all six v0.6 OpenAPI documents: Intake plus Evidence, Rider, Driver, Policy, and Gate;
- canonical accuracy-first manifest, Agent prompts, deployment guide, WorkBuddy adapter, and CI definition;
- refreshed 2026-10-15 Streamlit preview showing five-Agent reasoning;
- a generated `SUBMISSION_MANIFEST.json` with every included file's SHA-256 and size.

## Excluded

- all prior archives under `dist/` and the root legacy `RideResolve-Orchestration-import.zip`;
- `var/`, `.env`, local credentials, registries, caches, logs, raw CloudBase responses, and JSONL audit files;
- the two full `*.redacted.txt` process exports because they still reveal local absolute paths;
- unreviewed ADP, audit, trace, container, pod, workspace, run, request, and trace screenshots.

## Verification

- candidate archive: 133 entries, no duplicates, portable names;
- 24 JSON entries parsed successfully;
- all six `api/adp/v0_6/*.json` OpenAPI files present;
- every archived file matched the SHA-256 recorded in `SUBMISSION_MANIFEST.json`;
- privacy/secret scan found no blocked Windows user path, private key, JWT-like token, or Tencent-style secret ID in included text files;
- `python -m pytest -q -p no:cacheprovider --basetemp=.tmp_pytest_final`: 141 passed;
- `python -m unittest discover -s tests -q`: 133 passed;
- `python -m compileall -q app.py rideresolve scripts tests`: passed;
- `python -m pip check`: no broken requirements;
- local editable package metadata: `rideresolve 0.6.0`.
- unpacked candidate archive: full pytest suite and compilation both passed from the staged package tree.
- clean Python 3.12.14 environment: installed `requirements.lock`, installed `rideresolve 0.6.0`, passed 137 pytest tests and `pip check`, then removed the temporary environment.

## Final status

The mandatory WorkBuddy evidence gate was completed on 2026-10-16: three distinct, manually reviewed screenshots are present with a written development-process description and matching hashes in `privacy_review.json`. The final eligibility check passes. The final archive must be generated only after the release commit is created and pushed, and after temporary deployment credentials have been rotated or revoked.
