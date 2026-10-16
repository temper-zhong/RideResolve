#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "rideresolve-adp"
SERVER_VERSION = "0.6.0"
DEFAULT_CHAT_URL = "https://wss.lke.tencentcloud.com/adp/v2/chat"
SESSION_ID = re.compile(r"^[a-zA-Z0-9_-]{32,64}$")
ZERO_WIDTH = str.maketrans("", "", "\u200b\ufeff\u200c\u200d")


class AdpClientError(RuntimeError):
    pass


class AdpApiError(AdpClientError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        request_id: str = "",
        trace_id: str = "",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.request_id = request_id
        self.trace_id = trace_id

    def safe_message(self) -> str:
        parts = [f"ADP error {self.code}: {self.args[0]}"]
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        if self.trace_id:
            parts.append(f"trace_id={self.trace_id}")
        return "; ".join(parts)


@dataclass(frozen=True)
class AdpConfig:
    app_key: str
    chat_url: str = DEFAULT_CHAT_URL
    visitor_id: str = "workbuddy-user"
    timeout_seconds: float = 120.0

    @classmethod
    def from_environment(cls) -> "AdpConfig":
        app_key = os.environ.get("ADP_APP_KEY", "").strip()
        if not app_key:
            raise AdpClientError("ADP_APP_KEY is not configured")
        chat_url = os.environ.get("ADP_CHAT_URL", DEFAULT_CHAT_URL).strip()
        parsed = urlparse(chat_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AdpClientError("ADP_CHAT_URL must be an absolute HTTP(S) URL")
        visitor_id = os.environ.get("ADP_VISITOR_ID", "workbuddy-user").strip()
        if not visitor_id:
            raise AdpClientError("ADP_VISITOR_ID must not be empty")
        try:
            timeout = float(os.environ.get("ADP_TIMEOUT", "120"))
        except ValueError as exc:
            raise AdpClientError("ADP_TIMEOUT must be a number") from exc
        if timeout <= 0 or timeout > 600:
            raise AdpClientError("ADP_TIMEOUT must be between 0 and 600 seconds")
        return cls(
            app_key=app_key,
            chat_url=chat_url,
            visitor_id=visitor_id,
            timeout_seconds=timeout,
        )


def _clean_text(value: Any) -> str:
    return value.translate(ZERO_WIDTH) if isinstance(value, str) else ""


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _extract_completed_text(response: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in _as_list(response.get("Messages")):
        if not isinstance(message, dict) or message.get("Type") != "reply":
            continue
        for content in _as_list(message.get("Contents")):
            if isinstance(content, dict) and content.get("Type") == "text":
                text = _clean_text(content.get("Text"))
                if text:
                    parts.append(text)
    return "".join(parts)


def _normalize_usage(stat_info: Any) -> dict[str, Any]:
    stat = stat_info if isinstance(stat_info, dict) else {}
    return {
        "prompt_tokens": stat.get("InputTokens", 0),
        "completion_tokens": stat.get("OutputTokens", 0),
        "total_tokens": stat.get("TotalTokens", 0),
        "total_cost": stat.get("TotalCost", ""),
    }


def _normalize_procedures(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for procedure in _as_list(value):
        if not isinstance(procedure, dict):
            continue
        workflow = procedure.get("Workflow")
        workflow = workflow if isinstance(workflow, dict) else {}
        result.append(
            {
                "type": procedure.get("Type", ""),
                "name": procedure.get("Name", ""),
                "title": procedure.get("Title", ""),
                "status": procedure.get("Status", ""),
                "workflow_name": workflow.get("WorkflowName", ""),
                "workflow_run_id": workflow.get("WorkflowRunId", ""),
            }
        )
    return result


def iter_sse_frames(stream: BinaryIO) -> Iterable[tuple[str, str]]:
    event_name = ""
    data_lines: list[str] = []
    for raw_line in stream:
        line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
        if not line:
            if data_lines:
                yield event_name, "\n".join(data_lines)
            event_name = ""
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)
    if data_lines:
        yield event_name, "\n".join(data_lines)


def parse_adp_sse(stream: BinaryIO) -> dict[str, Any]:
    answer = ""
    references: list[Any] = []
    usage: dict[str, Any] = {}
    procedures: list[dict[str, Any]] = []
    response_request_id = ""
    trace_id = ""
    app_name = ""
    for event_name, data_text in iter_sse_frames(stream):
        if data_text == "[DONE]":
            break
        try:
            frame = json.loads(data_text)
        except json.JSONDecodeError as exc:
            raise AdpClientError("ADP returned a malformed SSE data frame") from exc
        if not isinstance(frame, dict):
            continue
        frame_type = str(frame.get("Type") or event_name)
        if frame_type == "error":
            error = frame.get("Error")
            error = error if isinstance(error, dict) else {}
            raise AdpApiError(
                str(error.get("Code", "UNKNOWN")),
                str(error.get("Message", "ADP request failed")),
                request_id=str(error.get("RequestId", "")),
                trace_id=str(error.get("TraceId", "")),
            )
        if frame_type == "text.delta":
            answer += _clean_text(frame.get("Text", frame.get("Content", "")))
            continue
        if frame_type == "text.replace":
            answer = _clean_text(frame.get("Text", frame.get("Content", "")))
            continue
        if frame_type == "reference.added":
            found = frame.get("References", frame.get("Reference", []))
            if isinstance(found, list):
                references.extend(found)
            elif isinstance(found, dict):
                references.append(found)
            continue
        if frame_type != "response.completed":
            continue
        response = frame.get("Response")
        response = response if isinstance(response, dict) else {}
        completed_text = _extract_completed_text(response)
        if completed_text:
            answer = completed_text
        found_references = response.get("References")
        if isinstance(found_references, list):
            references = found_references
        usage = _normalize_usage(response.get("StatInfo", response.get("Usage")))
        procedures = _normalize_procedures(response.get("Procedures"))
        extra = response.get("ExtraInfo")
        extra = extra if isinstance(extra, dict) else {}
        response_request_id = str(extra.get("RequestId", ""))
        trace_id = str(extra.get("TraceId", ""))
        app_name = str(extra.get("FromName", ""))
    return {
        "answer": answer,
        "references": references,
        "usage": usage,
        "procedures": procedures,
        "response_request_id": response_request_id,
        "trace_id": trace_id,
        "app_name": app_name,
    }


class AdpChatClient:
    def __init__(self, config: AdpConfig) -> None:
        self.config = config

    def chat(
        self,
        *,
        question: str,
        conversation_id: str | None = None,
        system_role: str | None = None,
        file_url: str | None = None,
        file_type: str = "file",
        file_name: str | None = None,
    ) -> dict[str, Any]:
        question = question.strip()
        if not question or len(question) > 8000:
            raise AdpClientError("question must contain between 1 and 8000 characters")
        if conversation_id is None:
            conversation_id = uuid.uuid4().hex
        if not SESSION_ID.fullmatch(conversation_id):
            raise AdpClientError(
                "Invalid conversation_id: expected 32-64 letters, numbers, underscores, or hyphens"
            )
        request_id = uuid.uuid4().hex
        contents: list[dict[str, Any]] = [{"Type": "text", "Text": question}]
        if file_url is not None:
            parsed = urlparse(file_url)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise AdpClientError("file_url must be an absolute HTTP(S) URL")
            if file_type not in {"file", "image"}:
                raise AdpClientError("file_type must be either file or image")
            attachment: dict[str, Any] = {"Type": file_type}
            if file_type == "image":
                attachment["ImageUrl"] = file_url
            else:
                attachment["FileUrl"] = file_url
                if file_name:
                    attachment["FileName"] = file_name
            contents.append(attachment)
        payload: dict[str, Any] = {
            "RequestId": request_id,
            "ConversationId": conversation_id,
            "AppKey": self.config.app_key,
            "VisitorId": self.config.visitor_id,
            "Contents": contents,
            "Stream": "enable",
            "Incremental": True,
        }
        if system_role:
            payload["SystemRole"] = system_role
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            self.config.chat_url,
            data=body,
            headers={
                "Accept": "text/event-stream",
                "Content-Type": "application/json; charset=utf-8",
            },
            method="POST",
        )
        started = time.perf_counter()
        try:
            with urlopen(request, timeout=self.config.timeout_seconds) as response:
                parsed_response = parse_adp_sse(response)
        except HTTPError as exc:
            raw = exc.read(8192).decode("utf-8", errors="replace")
            try:
                error_payload = json.loads(raw)
            except json.JSONDecodeError:
                error_payload = {}
            message = str(error_payload.get("message") or error_payload.get("Message") or exc.reason)
            raise AdpApiError(str(exc.code), message) from exc
        except URLError as exc:
            raise AdpClientError(f"ADP connection failed: {exc.reason}") from exc
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        return {
            "question": question,
            "answer": parsed_response["answer"],
            "conversation_id": conversation_id,
            "request_id": parsed_response["response_request_id"] or request_id,
            "references": parsed_response["references"],
            "usage": parsed_response["usage"],
            "procedures": parsed_response["procedures"],
            "duration_ms": duration_ms,
            "app_name": parsed_response["app_name"],
            "trace_id": parsed_response["trace_id"],
        }


TOOLS = [
    {
        "name": "adp_chat",
        "description": "Ask the published RideResolve ADP application a text question.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["question"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 8000},
                "conversation_id": {"type": "string", "minLength": 32, "maxLength": 64},
                "system_role": {"type": "string", "maxLength": 4000},
            },
        },
    },
    {
        "name": "adp_chat_with_file",
        "description": "Ask the published RideResolve ADP application with a file or image URL.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["question", "file_url"],
            "properties": {
                "question": {"type": "string", "minLength": 1, "maxLength": 8000},
                "file_url": {"type": "string", "minLength": 1, "maxLength": 4096},
                "file_type": {"type": "string", "enum": ["file", "image"], "default": "file"},
                "file_name": {"type": "string", "maxLength": 512},
                "conversation_id": {"type": "string", "minLength": 32, "maxLength": 64},
            },
        },
    },
]


def _tool_result(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def _tool_error(message: str) -> dict[str, Any]:
    return {"content": [{"type": "text", "text": message}], "isError": True}


def handle_tool_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    try:
        client = AdpChatClient(AdpConfig.from_environment())
        if name == "adp_chat":
            result = client.chat(
                question=str(arguments.get("question", "")),
                conversation_id=arguments.get("conversation_id"),
                system_role=arguments.get("system_role"),
            )
        elif name == "adp_chat_with_file":
            result = client.chat(
                question=str(arguments.get("question", "")),
                conversation_id=arguments.get("conversation_id"),
                file_url=arguments.get("file_url"),
                file_type=str(arguments.get("file_type", "file")),
                file_name=arguments.get("file_name"),
            )
        else:
            return _tool_error(f"Unknown tool: {name}")
        return _tool_result(result)
    except AdpApiError as exc:
        return _tool_error(exc.safe_message())
    except AdpClientError as exc:
        return _tool_error(str(exc))
    except Exception:
        return _tool_error("Unexpected connector failure; see local WorkBuddy logs")


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params")
        params = params if isinstance(params, dict) else {}
        return {"jsonrpc": "2.0", "id": request_id, "result": handle_tool_call(params)}
    if method == "ping":
        return {"jsonrpc": "2.0", "id": request_id, "result": {}}
    if request_id is None:
        return None
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    sys.stderr.write(
        f"{SERVER_NAME} {SERVER_VERSION} starting; ADP_APP_KEY="
        f"{'set' if os.environ.get('ADP_APP_KEY') else 'not-set'}\n"
    )
    sys.stderr.flush()
    for line in sys.stdin:
        try:
            message = json.loads(line)
            if not isinstance(message, dict):
                continue
            response = handle_request(message)
        except json.JSONDecodeError:
            continue
        except Exception:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": "Internal server error"},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=True) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()

