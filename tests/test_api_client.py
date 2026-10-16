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
"""OAuth exchange, paging and tool behaviour against a mocked API (no network)."""

import base64
import json
from urllib.parse import parse_qs

import httpx
import pytest

from alternative_payments_mcp import api_client
from alternative_payments_mcp.api_client import AltPayClient, AltPayCredentials
from alternative_payments_mcp.server import _credentials_var, create_mcp_server

INVOICE_PAGE = {
    "data": [{"id": "inv_1", "status": "OVERDUE", "amount": 1250.0}],
    "end_cursor": "cur_2",
    "has_next_page": True,
    "has_previous_page": False,
    "start_cursor": "cur_1",
}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(api_client.asyncio, "sleep", instant)


class FakeApi:
    """Records requests; answers the token call and then ``reply``."""

    def __init__(self, reply=None, token_status=200):
        self.requests: list[httpx.Request] = []
        self.reply = reply or (lambda r: httpx.Response(200, json={"data": [], "has_next_page": False}))
        self.token_status = token_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/oauth/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "server_error"})
            return httpx.Response(200, json={"access_token": "tok-123", "expires_in": 3600, "token_type": "Bearer"})
        return self.reply(request)

    def api_requests(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path != "/oauth/token"]


async def _call(monkeypatch, fake: FakeApi, tool: str, args: dict, environment: str = "production"):
    http = httpx.AsyncClient(transport=httpx.MockTransport(fake))
    monkeypatch.setattr(api_client, "_get_shared_http_client", lambda: http)
    mcp = create_mcp_server()
    ctx = _credentials_var.set(AltPayCredentials("cid", "csecret", environment))
    try:
        content, _ = await mcp.call_tool(tool, args)
    finally:
        _credentials_var.reset(ctx)
    return json.loads(content[0].text)


async def test_token_exchange_uses_basic_auth_form_then_bearer(monkeypatch):
    fake = FakeApi(lambda r: httpx.Response(200, json=INVOICE_PAGE))
    result = await _call(monkeypatch, fake, "ap_list_invoices", {"status": "OVERDUE", "limit": 500})

    token_req, api_req = fake.requests
    assert str(token_req.url) == "https://public-api.alternativepayments.io/oauth/token"
    assert token_req.headers["authorization"] == "Basic " + base64.b64encode(b"cid:csecret").decode()
    assert parse_qs(token_req.content.decode()) == {"grant_type": ["client_credentials"]}
    assert api_req.headers["authorization"] == "Bearer tok-123"
    assert "csecret" not in str(api_req.headers)
    assert api_req.url.params["status"] == "OVERDUE"
    assert api_req.url.params["limit"] == "100"  # clamped
    assert result == {
        "items": [{"id": "inv_1", "status": "OVERDUE", "amount": 1250.0}],
        "count": 1,
        "has_more": True,
        "next_cursor": "cur_2",
    }


async def test_token_fetched_once_per_client():
    fake = FakeApi()
    client = AltPayClient(AltPayCredentials("a", "b"), http_client=httpx.AsyncClient(transport=httpx.MockTransport(fake)))
    await client.get("/customers")
    await client.get("/invoices")
    assert [r.url.path for r in fake.requests].count("/oauth/token") == 1


async def test_bad_credentials_map_to_unauthorized(monkeypatch):
    result = await _call(monkeypatch, FakeApi(token_status=403), "ap_status", {})
    assert result["error"]["code"] == "unauthorized"
    assert "csecret" not in json.dumps(result)


async def test_demo_environment_host(monkeypatch):
    fake = FakeApi()
    await _call(monkeypatch, fake, "ap_list_customers", {}, environment="demo")
    assert {r.url.host for r in fake.requests} == {"public-api.demo.alternativepayments.io"}


async def test_create_invoice_body(monkeypatch):
    fake = FakeApi(lambda r: httpx.Response(201, json={"data": {"id": "inv_9"}}))
    result = await _call(
        monkeypatch,
        fake,
        "ap_create_invoice",
        {
            "customer_id": "cus_1",
            "currency": "usd",
            "due_date": "2026-11-30",
            "line_items": [{"description": "Managed services", "amount": 1200, "quantity": 1}],
        },
    )
    req = fake.api_requests()[0]
    assert (req.method, req.url.path) == ("POST", "/invoices")
    assert json.loads(req.content) == {
        "customer_id": "cus_1",
        "currency": "USD",
        "due_date": "2026-11-30",
        "line_items": [{"description": "Managed services", "amount": 1200.0, "quantity": 1}],
    }
    assert result == {"id": "inv_9"}


@pytest.mark.parametrize(
    "args",
    [
        {"customer_id": "c", "currency": "EUR", "due_date": "2026-11-30", "line_items": [{"description": "x", "amount": 1}]},
        {"customer_id": "c", "currency": "USD", "due_date": "30/11/2026", "line_items": [{"description": "x", "amount": 1}]},
    ],
)
async def test_create_invoice_rejects_bad_input_without_calling_api(monkeypatch, args):
    fake = FakeApi()
    result = await _call(monkeypatch, fake, "ap_create_invoice", args)
    assert result["error"]["code"] == "invalid_argument"
    assert fake.requests == []


async def test_payment_request_sends_amount_as_string(monkeypatch):
    fake = FakeApi(lambda r: httpx.Response(200, json={"id": "pr_1", "url": "https://example.com/pay"}))
    await _call(
        monkeypatch,
        fake,
        "ap_create_payment_request",
        {"amount": 250, "currency": "USD", "redirect_url": "https://example.com/done", "reference_id": "ref-1"},
    )
    req = fake.api_requests()[0]
    assert (req.method, req.url.path) == ("POST", "/payments/request")
    assert json.loads(req.content) == {"amount": "250.00", "redirect_url": "https://example.com/done", "reference_id": "ref-1"}


@pytest.mark.parametrize(
    "tool,args,method,path",
    [
        ("ap_archive_customer", {"id": "cus_1"}, "DELETE", "/customers/cus_1"),
        ("ap_archive_invoice", {"id": "inv_1"}, "DELETE", "/invoices/inv_1"),
        ("ap_delete_webhook", {"subscription_id": "sub_1"}, "DELETE", "/webhooks/sub_1"),
        ("ap_retry_webhooks", {}, "POST", "/webhooks/retry"),
        ("ap_list_transactions", {"type": "refund"}, "GET", "/payments"),
        ("ap_get_transaction", {"id": "pay_1"}, "GET", "/payments/pay_1"),
        ("ap_list_payout_transactions", {"id": "po_1"}, "GET", "/payouts/po_1/transactions"),
        ("ap_get_payment_request", {"id": "pr_1"}, "GET", "/payments/request/pr_1"),
        ("ap_list_webhook_events", {"status": "failed"}, "GET", "/webhooks/events"),
    ],
)
async def test_endpoint_routing(monkeypatch, tool, args, method, path):
    fake = FakeApi(lambda r: httpx.Response(200, json={}))
    result = await _call(monkeypatch, fake, tool, args)
    req = fake.api_requests()[0]
    assert (req.method, req.url.path) == (method, path)
    assert "error" not in result


async def test_create_webhook_requires_https(monkeypatch):
    fake = FakeApi()
    result = await _call(monkeypatch, fake, "ap_create_webhook", {"endpoint_url": "http://example.com/hook", "topic": "invoice_paid"})
    assert result["error"]["code"] == "invalid_argument"
    assert fake.requests == []
