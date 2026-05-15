import json

import pytest

from cloak_relay.mcp_server import MCPServer, parse_jsonrpc_messages


def test_parse_newline_jsonrpc_message():
    payload = b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n'
    assert parse_jsonrpc_messages(payload) == [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    ]


def test_parse_content_length_jsonrpc_message():
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"}).encode()
    payload = b"Content-Length: " + str(len(body)).encode() + b"\r\n\r\n" + body
    assert parse_jsonrpc_messages(payload) == [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    ]


class FakeHTTPClient:
    def __init__(self):
        self.calls = []

    def get(self, path):
        self.calls.append(("GET", path, None))
        return {"ok": True}

    def post(self, path, body):
        self.calls.append(("POST", path, body))
        return {"ok": True, "path": path, "body": body}


def test_tools_list_contains_navigation_tool():
    server = MCPServer(FakeHTTPClient())
    response = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    names = [tool["name"] for tool in response["result"]["tools"]]
    assert "browser_navigate" in names


def test_tools_call_forwards_to_http_api():
    client = FakeHTTPClient()
    server = MCPServer(client)
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "browser_navigate",
                "arguments": {"url": "https://example.com"},
            },
        }
    )
    assert client.calls == [("POST", "/api/navigate", {"url": "https://example.com"})]
    assert response["result"]["content"][0]["type"] == "text"
    assert '"ok": true' in response["result"]["content"][0]["text"]


def test_unknown_tool_returns_jsonrpc_error():
    server = MCPServer(FakeHTTPClient())
    response = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "missing", "arguments": {}},
        }
    )
    assert response["error"]["code"] == -32601
