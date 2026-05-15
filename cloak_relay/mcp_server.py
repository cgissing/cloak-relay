from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, BinaryIO, Iterable


def object_schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


TOOL_SPECS: dict[str, dict[str, Any]] = {
    "browser_health": {
        "method": "GET",
        "path": "/health",
        "description": "Check whether the Cloak Relay HTTP service is alive.",
        "schema": {"type": "object", "properties": {}},
    },
    "browser_tabs": {
        "method": "GET",
        "path": "/api/tabs",
        "description": "List active Cloak Relay sessions and pages.",
        "schema": {"type": "object", "properties": {}},
    },
    "browser_start_session": {
        "method": "POST",
        "path": "/api/session/start",
        "description": "Start or reuse a CloakBrowser session.",
        "schema": object_schema(
            {
                "sessionId": {"type": "string"},
                "headless": {"type": "boolean"},
                "humanize": {"type": "boolean"},
                "profile": {"type": "string"},
                "proxy": {"type": "string"},
                "geoip": {"type": "boolean"},
                "locale": {"type": "string"},
                "timezone": {"type": "string"},
                "humanPreset": {"type": "string"},
            }
        ),
    },
    "browser_close_session": {
        "method": "POST",
        "path": "/api/session/close",
        "description": "Close a CloakBrowser session without deleting the profile.",
        "schema": object_schema({"sessionId": {"type": "string"}}),
    },
    "browser_clear_session": {
        "method": "POST",
        "path": "/api/session/clear",
        "description": "Close a session and delete its managed profile directory.",
        "schema": object_schema({"sessionId": {"type": "string"}}),
    },
    "browser_navigate": {
        "method": "POST",
        "path": "/api/navigate",
        "description": "Navigate a session page to a URL.",
        "schema": object_schema(
            {"sessionId": {"type": "string"}, "url": {"type": "string"}},
            required=["url"],
        ),
    },
    "browser_snapshot": {
        "method": "GET",
        "path": "/api/snapshot",
        "description": "Read a text or HTML snapshot of the current page.",
        "schema": object_schema(
            {"sessionId": {"type": "string"}, "format": {"type": "string", "enum": ["text", "html"]}}
        ),
    },
    "browser_click": {
        "method": "POST",
        "path": "/api/click",
        "description": "Click a selector through CloakBrowser's humanized Playwright actions.",
        "schema": object_schema(
            {
                "sessionId": {"type": "string"},
                "selector": {"type": "string"},
                "doubleClick": {"type": "boolean"},
            },
            required=["selector"],
        ),
    },
    "browser_type": {
        "method": "POST",
        "path": "/api/type",
        "description": "Type text into a selector through CloakBrowser's humanized Playwright actions.",
        "schema": object_schema(
            {
                "sessionId": {"type": "string"},
                "selector": {"type": "string"},
                "text": {"type": "string"},
                "clear": {"type": "boolean"},
                "submit": {"type": "boolean"},
            },
            required=["selector", "text"],
        ),
    },
    "browser_scroll": {
        "method": "POST",
        "path": "/api/scroll",
        "description": "Scroll with page mouse wheel actions.",
        "schema": object_schema(
            {
                "sessionId": {"type": "string"},
                "direction": {"type": "string", "enum": ["up", "down", "left", "right"]},
                "amount": {"type": "integer"},
            }
        ),
    },
    "browser_screenshot": {
        "method": "POST",
        "path": "/api/screenshot",
        "description": "Capture a PNG screenshot and return base64 data.",
        "schema": object_schema({"sessionId": {"type": "string"}, "fullPage": {"type": "boolean"}}),
    },
    "browser_eval": {
        "method": "POST",
        "path": "/api/eval",
        "description": "Evaluate JavaScript in the current page. Local-only debug escape hatch.",
        "schema": object_schema(
            {"sessionId": {"type": "string"}, "expression": {"type": "string"}},
            required=["expression"],
        ),
    },
}


@dataclass
class HTTPClient:
    base_url: str

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        query = urllib.parse.urlencode(clean_params(params or {}))
        suffix = f"{path}?{query}" if query else path
        return self._request("GET", suffix)

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        return self._request("POST", path, body or {})

    def _request(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        url = self.base_url.rstrip("/") + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(raw or str(exc)) from exc
        return json.loads(raw) if raw else {}


class MCPServer:
    def __init__(self, http_client: Any) -> None:
        self.http_client = http_client

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        message_id = message.get("id")
        try:
            if method == "initialize":
                return self.response(message_id, self.initialize_result())
            if method == "tools/list":
                return self.response(message_id, {"tools": self.tools()})
            if method == "tools/call":
                return self.response(message_id, self.call_tool(message.get("params") or {}))
            if method and method.startswith("notifications/"):
                return None
            return self.error(message_id, -32601, f"unknown method: {method}")
        except Exception as exc:
            return self.error(message_id, -32000, str(exc))

    def initialize_result(self) -> dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "cloak-relay-mcp", "version": "0.1.0"},
        }

    def tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": name,
                "description": spec["description"],
                "inputSchema": spec["schema"],
            }
            for name, spec in TOOL_SPECS.items()
        ]

    def call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in TOOL_SPECS:
            raise UnknownToolError(f"unknown tool: {name}")
        spec = TOOL_SPECS[name]
        if spec["method"] == "GET":
            result = self.http_client.get(spec["path"], args)
        else:
            result = self.http_client.post(spec["path"], args)
        return {
            "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
            "isError": False,
        }

    def response(self, message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    def error(self, message_id: Any, code: int, message: str) -> dict[str, Any]:
        if message.startswith("unknown tool:"):
            code = -32601
        return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


class UnknownToolError(Exception):
    pass


def clean_params(params: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in params.items() if value is not None}


def parse_jsonrpc_messages(payload: bytes) -> list[dict[str, Any]]:
    payload = payload.strip()
    if not payload:
        return []
    if payload.lower().startswith(b"content-length:"):
        header, body = payload.split(b"\r\n\r\n", 1)
        length = None
        for line in header.splitlines():
            if line.lower().startswith(b"content-length:"):
                length = int(line.split(b":", 1)[1].strip())
                break
        if length is None:
            raise ValueError("missing Content-Length")
        return [json.loads(body[:length].decode("utf-8"))]
    return [json.loads(line.decode("utf-8")) for line in payload.splitlines() if line.strip()]


def iter_messages(stream: BinaryIO) -> Iterable[dict[str, Any]]:
    while True:
        line = stream.readline()
        if not line:
            break
        if not line.strip():
            continue
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())
            while True:
                header_line = stream.readline()
                if header_line in {b"\r\n", b"\n", b""}:
                    break
            body = stream.read(length)
            yield json.loads(body.decode("utf-8"))
        else:
            yield json.loads(line.decode("utf-8"))


def write_message(stream: BinaryIO, message: dict[str, Any]) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body)
    stream.flush()


def run_stdio(base_url: str) -> None:
    server = MCPServer(HTTPClient(base_url))
    for message in iter_messages(sys.stdin.buffer):
        response = server.handle(message)
        if response is not None:
            write_message(sys.stdout.buffer, response)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Cloak Relay MCP stdio bridge.")
    parser.add_argument("--url", default=os.environ.get("CLOAK_RELAY_URL", "http://127.0.0.1:18796"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_arg_parser().parse_args(argv)
    run_stdio(args.url)


if __name__ == "__main__":
    main()
