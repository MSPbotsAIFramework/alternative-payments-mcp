# Copyright 2026 MSPbots.ai
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Credential middleware: 401 on missing headers, environment, isolation."""

import asyncio

import pytest
from starlette.testclient import TestClient

from alternative_payments_mcp.__main__ import build_http_app
from alternative_payments_mcp.server import (
    GatewayCredentialsMiddleware,
    _credentials_var,
    create_mcp_server,
    get_client_from_context,
)

MCP_HEADERS = {"Accept": "application/json, text/event-stream"}
CREDS = {"X-Alternative-Payments-Client-Id": "your-client-id", "X-Alternative-Payments-Client-Secret": "YOUR_SECRET"}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}


def _client() -> TestClient:
    return TestClient(build_http_app(create_mcp_server()))


def test_health_is_local():
    with _client() as client:
        resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize("drop", list(CREDS))
def test_missing_header_returns_401(drop):
    headers = MCP_HEADERS | {k: v for k, v in CREDS.items() if k != drop}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=headers)
    assert resp.status_code == 401
    assert resp.json()["required_headers"] == list(CREDS)
    assert drop in resp.json()["message"]


def test_unknown_environment_returns_400():
    headers = MCP_HEADERS | CREDS | {"X-Alternative-Payments-Environment": "staging"}
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=headers)
    assert resp.status_code == 400
    assert resp.json()["allowed_values"] == ["production", "demo"]


def test_tools_list_over_http():
    with _client() as client:
        resp = client.post("/mcp", json=LIST_TOOLS, headers=MCP_HEADERS | CREDS)
    assert resp.status_code == 200
    assert "ap_list_invoices" in resp.text


def _run_middleware(headers: list[tuple[bytes, bytes]]) -> dict:
    seen: dict = {}

    async def app(scope, receive, send):
        seen["credentials"] = _credentials_var.get()
        seen["client"] = get_client_from_context()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    asyncio.run(GatewayCredentialsMiddleware(app)({"type": "http", "path": "/mcp", "headers": headers}, receive, send))
    return seen


BASE = [(b"x-alternative-payments-client-id", b"id"), (b"x-alternative-payments-client-secret", b"secret")]


@pytest.mark.parametrize(
    "value,host",
    [
        (None, "public-api.alternativepayments.io"),
        (b"production", "public-api.alternativepayments.io"),
        (b"Demo", "public-api.demo.alternativepayments.io"),
    ],
)
def test_environment_selects_host(value, host):
    headers = BASE + ([(b"x-alternative-payments-environment", value)] if value is not None else [])
    seen = _run_middleware(headers)
    assert seen["client"].base_url == f"https://{host}"
    assert _credentials_var.get() is None


def test_concurrent_requests_do_not_share_credentials():
    observed: list[tuple[str, str]] = []

    async def app(scope, receive, send):
        before = _credentials_var.get().client_id
        await asyncio.sleep(0.01)
        observed.append((before, _credentials_var.get().client_id))
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(_message):
        return None

    middleware = GatewayCredentialsMiddleware(app)

    def scope(cid: bytes) -> dict:
        return {
            "type": "http",
            "path": "/mcp",
            "headers": [(b"x-alternative-payments-client-id", cid), (b"x-alternative-payments-client-secret", b"s")],
        }

    async def both():
        await asyncio.gather(middleware(scope(b"tenant-a"), receive, send), middleware(scope(b"tenant-b"), receive, send))

    asyncio.run(both())
    assert sorted(observed) == [("tenant-a", "tenant-a"), ("tenant-b", "tenant-b")]


def test_credentials_repr_hides_secrets():
    seen = _run_middleware(
        [(b"x-alternative-payments-client-id", b"secret-id"), (b"x-alternative-payments-client-secret", b"secret-value")]
    )
    text = repr(seen["credentials"])
    assert "secret-id" not in text and "secret-value" not in text
