# Submission package report

Prepared: 2026-10-16

Final archive: `dist/RR-submit-final-v0.6.0-r2.zip`

Status: **final submission package; use this revision instead of earlier candidate or final archives**

SHA-256: `D9CFE46120ABB850637649CDBCC2F9395EBEE9304784E44D0E7E96E6A823E023`

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
- a standalone 1920x1080 architecture diagram under `docs/assets/`;
- refreshed 2026-10-15 Streamlit preview showing five-Agent reasoning;
- a generated `SUBMISSION_MANIFEST.json` with every included file's SHA-256 and size.

## Excluded

- all prior archives under `dist/` and the root legacy `RideResolve-Orchestration-import.zip`;
- `var/`, `.env`, local credentials, registries, caches, logs, raw CloudBase responses, and JSONL audit files;
- the two full `*.redacted.txt` process exports because they still reveal local absolute paths;
- unreviewed ADP, audit, trace, container, pod, workspace, run, request, and trace screenshots.

## Verification

- final archive: 140 ZIP entries comprising 139 packaged files plus `SUBMISSION_MANIFEST.json`, with no duplicates and portable names;
- 25 JSON entries parsed successfully;
- all six `api/adp/v0_6/*.json` OpenAPI files present;
- every archived file matched the SHA-256 recorded in `SUBMISSION_MANIFEST.json`;
- privacy/secret scan found no blocked Windows user path, private key, JWT-like token, or Tencent-style secret ID in included text files;
- `python -m pytest -q -p no:cacheprovider --basetemp=.tmp_pytest_r2`: 141 passed;
- `python -m unittest discover -s tests -q`: 137 passed;
- `python -m compileall -q app.py rideresolve scripts tests`: passed;
- `python -m pip check`: no broken requirements;
- local editable package metadata: `rideresolve 0.6.0`.
- every one of the 139 packaged files matched the SHA-256 stored in `SUBMISSION_MANIFEST.json`.
- clean Python 3.12.14 environment: installed `requirements.lock`, installed `rideresolve 0.6.0`, passed the then-current test suite and `pip check`, then removed the temporary environment.

## Final status

The mandatory WorkBuddy evidence gate was completed on 2026-10-16: three distinct, manually reviewed screenshots are present with a written development-process description and matching hashes in `privacy_review.json`. The final eligibility check passes, temporary AppKey rotation has been completed, and the final r2 archive has been generated and verified. Before submitting the form, confirm that the GitHub repository is publicly readable without cached credentials.
