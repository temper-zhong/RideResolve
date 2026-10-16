# Submission package report

Prepared: 2026-10-16

Current archive: `dist/RR-submit-candidate-v0.6.0-r5-prompt-sync.zip`

Status: **candidate only; do not submit until the official-case Synthetic label defect is fixed and a new final archive is generated**

SHA-256: `ACA9657DB77ED1FBA1C2EB7D073AEEB2015AB6C33C8384E10ED5D5342D1CB6FA`

## Canonical architecture

The package declares one public entry path:

`SYS.UserQuery -> guarded Intake -> signed internal run context -> five strictly serial tool-free Agents -> deterministic Gate -> one End`

The user supplies a normal problem description containing an explicit official `DISP-*`, synthetic `DEMO-*`, or corresponding `TRIP-*` reference. The system creates `run_id` internally. Official data and synthetic public demonstrations remain separately labeled, and official data overrides any conflicting synthetic identity.

`docs/adp/multiagent_manifest.json` is included only as an explicitly marked, unvalidated historical experiment. It is not the submitted architecture.

## Included

- current v0.6 source, official/synthetic datasets, tests, and reproducibility lock file;
- nine explicitly labeled synthetic public demos covering common Route Deviation, No-Show, and Fare Dispute outcomes;
- the signed-session expiry precision fix that prevents valid Intake contexts with microseconds
  from being rejected by downstream tools as HTTP 401;
- all six v0.6 OpenAPI documents: Intake plus Evidence, Rider, Driver, Policy, and Gate;
- canonical accuracy-first manifest, the current public Coordinator prompt, all five specialist
  Agent prompts, deployment guide, WorkBuddy adapter, and CI definition;
- submission copy that maps the five-Agent architecture and twelve public cases to the official
  challenge requirements and stretch goals;
- a standalone 1920x1080 architecture diagram under `docs/assets/`;
- refreshed 2026-10-15 Streamlit preview showing five-Agent reasoning;
- a generated `SUBMISSION_MANIFEST.json` with every included file's SHA-256 and size.

## Excluded

- all prior archives under `dist/` and the root legacy `RideResolve-Orchestration-import.zip`;
- `var/`, `.env`, local credentials, registries, caches, logs, raw CloudBase responses, and JSONL audit files;
- the two full `*.redacted.txt` process exports because they still reveal local absolute paths;
- unreviewed ADP, audit, trace, container, pod, workspace, run, request, and trace screenshots.

## Verification

- candidate archive: 145 ZIP entries comprising 144 packaged files plus `SUBMISSION_MANIFEST.json`, with no duplicates and portable names;
- 25 JSON entries parsed successfully;
- all six `api/adp/v0_6/*.json` OpenAPI files present;
- every archived file matched the SHA-256 recorded in `SUBMISSION_MANIFEST.json`;
- privacy/secret scan found no blocked Windows user path, private key, JWT-like token, or Tencent-style secret ID in included text files;
- `python -m pytest -q --basetemp=.tmp_pytest_demo_expansion_2`: 148 passed;
- `python -m unittest discover -s tests -v`: 144 passed;
- `python -m compileall -q app.py rideresolve scripts tests`: passed;
- `python -m pip check`: no broken requirements;
- local editable package metadata: `rideresolve 0.6.0`.
- every one of the 144 packaged files matched the SHA-256 stored in `SUBMISSION_MANIFEST.json`.
- clean Python 3.12.14 environment: installed `requirements.lock`, installed `rideresolve 0.6.0`, passed the then-current test suite and `pip check`, then removed the temporary environment.

## Final status

The mandatory WorkBuddy evidence gate was completed on 2026-10-16: three distinct, manually reviewed screenshots are present with a written development-process description and matching hashes in `privacy_review.json`. The r4 archive is retired because it predates the final ADP prompt synchronization and updated challenge mapping. The verified r5 archive is intentionally marked `CANDIDATE_NOT_FOR_SUBMISSION`; after the official-case Synthetic label defect is fixed, rerun the full tests, generate the next final archive with `--final`, and confirm that the GitHub repository is publicly readable without cached credentials.
