from __future__ import annotations

import io
import json
import os
import threading
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from integrations.workbuddy.adp_mcp_server import (
    AdpApiError,
    AdpChatClient,
    AdpClientError,
    AdpConfig,
    handle_request,
    parse_adp_sse,
)


def _sse(event: str, payload: dict) -> bytes:
    return (
        f"event: {event}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    ).encode("utf-8")


COMPLETED_STREAM = (
    _sse("text.delta", {"Type": "text.delta", "Text": "\u200bPartial "})
    + _sse("text.delta", {"Type": "text.delta", "Text": "answer"})
    + _sse(
        "response.completed",
        {
            "Type": "response.completed",
            "Response": {
                "Messages": [
                    {
                        "Type": "reply",
                        "Contents": [{"Type": "text", "Text": "Validated final answer"}],
                    }
                ],
                "References": [{"Name": "Official source", "Type": "doc"}],
                "Procedures": [
                    {
                        "Type": "workflow",
                        "Name": "workflow",
                        "Status": "success",
                        "Workflow": {
                            "WorkflowName": "RideResolve Accuracy First",
                            "WorkflowRunId": "wfr-test-001",
                        },
                    }
                ],
                "StatInfo": {
                    "InputTokens": 12,
                    "OutputTokens": 4,
                    "TotalTokens": 16,
                    "TotalCost": "0.01",
                },
                "ExtraInfo": {
                    "RequestId": "request-from-adp-0000000000000001",
                    "TraceId": "trace-test",
                    "FromName": "RideResolve",
                },
            },
        },
    )
    + b"event: done\ndata: [DONE]\n\n"
)

REPLACE_STREAM = (
    _sse("text.delta", {"Type": "text.delta", "Text": "draft"})
    + _sse("text.replace", {"Type": "text.replace", "Text": "\ufeffrevised"})
    + b"event: done\ndata: [DONE]\n\n"
)

ERROR_STREAM = (
    _sse(
        "error",
        {
            "Type": "error",
            "Error": {
                "Code": 460011,
                "Message": "concurrency limit",
                "RequestId": "safe-request",
                "TraceId": "safe-trace",
            },
        },
    )
    + b"event: done\ndata: [DONE]\n\n"
)


class MockHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        self.__class__.requests.append(body)
        stream = ERROR_STREAM if self.path == "/error" else COMPLETED_STREAM
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(stream)))
        self.end_headers()
        self.wfile.write(stream)

    def log_message(self, format: str, *args: object) -> None:
        return


@contextmanager
def mock_server():
    MockHandler.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class SseParserTests(unittest.TestCase):
    def test_top_level_frames_and_completed_fallback_are_parsed(self) -> None:
        result = parse_adp_sse(io.BytesIO(COMPLETED_STREAM))
        self.assertEqual("Validated final answer", result["answer"])
        self.assertEqual(16, result["usage"]["total_tokens"])
        self.assertEqual("wfr-test-001", result["procedures"][0]["workflow_run_id"])
        self.assertEqual("RideResolve", result["app_name"])

    def test_text_replace_replaces_and_zero_width_characters_are_removed(self) -> None:
        result = parse_adp_sse(io.BytesIO(REPLACE_STREAM))
        self.assertEqual("revised", result["answer"])

    def test_error_event_propagates_safe_fields(self) -> None:
        with self.assertRaises(AdpApiError) as caught:
            parse_adp_sse(io.BytesIO(ERROR_STREAM))
        self.assertEqual("460011", caught.exception.code)
        self.assertIn("safe-trace", caught.exception.safe_message())


class AdpClientTests(unittest.TestCase):
    def test_chat_sends_required_fields_and_reuses_session(self) -> None:
        conversation_id = "session_123456789012345678901234"
        with mock_server() as base_url:
            client = AdpChatClient(
                AdpConfig(
                    app_key="secret-app-key",
                    chat_url=base_url + "/chat",
                    visitor_id="visitor",
                    timeout_seconds=5,
                )
            )
            result = client.chat(
                question="Please review DISP-001",
                conversation_id=conversation_id,
            )
        sent = MockHandler.requests[-1]
        self.assertEqual(conversation_id, sent["ConversationId"])
        self.assertEqual("secret-app-key", sent["AppKey"])
        self.assertEqual("enable", sent["Stream"])
        self.assertTrue(sent["Incremental"])
        self.assertEqual("text", sent["Contents"][0]["Type"])
        self.assertEqual("Validated final answer", result["answer"])
        self.assertEqual(conversation_id, result["conversation_id"])

    def test_file_payload_uses_documented_carrier_fields(self) -> None:
        with mock_server() as base_url:
            client = AdpChatClient(
                AdpConfig(app_key="key", chat_url=base_url + "/chat", timeout_seconds=5)
            )
            client.chat(
                question="Review this image",
                file_url="https://example.invalid/image.png",
                file_type="image",
            )
        self.assertEqual(
            {"Type": "image", "ImageUrl": "https://example.invalid/image.png"},
            MockHandler.requests[-1]["Contents"][1],
        )

    def test_invalid_conversation_id_fails_before_network(self) -> None:
        client = AdpChatClient(AdpConfig(app_key="key", chat_url="http://127.0.0.1:1"))
        with self.assertRaisesRegex(AdpClientError, "Invalid conversation_id"):
            client.chat(question="hello", conversation_id="too-short")

    def test_api_error_is_returned_from_sse(self) -> None:
        with mock_server() as base_url:
            client = AdpChatClient(
                AdpConfig(app_key="key", chat_url=base_url + "/error", timeout_seconds=5)
            )
            with self.assertRaises(AdpApiError) as caught:
                client.chat(question="hello")
        self.assertEqual("460011", caught.exception.code)


class McpProtocolTests(unittest.TestCase):
    def test_initialize_and_tool_discovery(self) -> None:
        initialized = handle_request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual("rideresolve-adp", initialized["result"]["serverInfo"]["name"])
        listed = handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        self.assertEqual(
            {"adp_chat", "adp_chat_with_file"},
            {item["name"] for item in listed["result"]["tools"]},
        )

    def test_missing_app_key_is_reported_without_throwing_json_rpc(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            response = handle_request(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "adp_chat", "arguments": {"question": "hello"}},
                }
            )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("ADP_APP_KEY is not configured", response["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
