# Submission-safe process records

The two `*.redacted.txt` files in this directory are sanitized copies of local development transcripts. The raw source files under the workspace-level `gpt对话/` directory were deliberately left unchanged to preserve the original record.

Sanitization performed on 2026-10-11:

- known locally issued Rider/Driver/Judge role credentials were replaced with `<REDACTED_ROLE_TOKEN>`;
- additional assigned API/App key-like values were replaced with `<REDACTED_SECRET>`;
- the sanitized copies were checked again for those known token values and assignment patterns.

Do not submit the raw source transcripts. The two full `*.redacted.txt` exports are also excluded from the submission package: automated redaction did not remove every local absolute path, and full histories expose unnecessary private context. Use only a small set of separately captured, manually reviewed CodeBuddy/WorkBuddy screenshots under `docs/process_records/submission/`.
