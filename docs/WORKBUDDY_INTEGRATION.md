# WorkBuddy integration handoff

## What is ready

`integrations/workbuddy/adp_mcp_server.py` is a Python-standard-library MCP server that exposes:

- `adp_chat`
- `adp_chat_with_file`

It calls the published Tencent Cloud ADP Chat API over HTTP SSE, assembles top-level `text.delta`
and `text.replace` frames, strips zero-width characters, and returns the answer, conversation ID,
request ID, references, token usage, procedures, application name, trace ID, and workflow run ID.

## What still requires the ADP console

1. Deploy the v0.6 service and update the ADP workflow.
2. Run the acceptance tests in `docs/adp/ACCURACY_FIRST_DEPLOYMENT.md`.
3. Publish the ADP application.
4. Copy the published application AppKey. Do not use an OpenAPI connector secret as the AppKey.

The Chat API cannot publish or edit an ADP application. It invokes an already-published version.

## WorkBuddy configuration

Copy `integrations/workbuddy/mcp.windows.template.json` into the existing WorkBuddy MCP
configuration and replace only:

- the Python executable path;
- `REPLACE_WITH_PUBLISHED_ADP_APP_KEY`.

Use a unique `conversation_id` per end-user session. Reuse it only for the next turn by the same
user. Never share one conversation ID between users.

After restarting WorkBuddy, enable the `rideresolve-adp` MCP server and verify that both tools are
listed. The first real smoke test should include an explicit official case or trip reference; a
description without one is expected to ask for clarification.

## Secret handling

- Keep `ADP_APP_KEY` only in the WorkBuddy MCP environment block or a local secret manager.
- Do not commit a populated `mcp.json`.
- Do not print the key, user question, or full request body to logs.
- Rotate the AppKey if it appears in chat, screenshots, exported traces, or source control.

