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
"""FastMCP factory and the per-request credential middleware."""

import contextvars
import uuid
from collections.abc import Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from .api_client import AltPayClient, AltPayCredentials
from .config import DEFAULT_ENVIRONMENT, ENVIRONMENT_BASE_URLS, Settings

HEADER_CLIENT_ID = "X-Alternative-Payments-Client-Id"
HEADER_CLIENT_SECRET = "X-Alternative-Payments-Client-Secret"
HEADER_ENVIRONMENT = "X-Alternative-Payments-Environment"
REQUIRED_HEADERS = [HEADER_CLIENT_ID, HEADER_CLIENT_SECRET]
OPTIONAL_HEADERS = [HEADER_ENVIRONMENT]

# Per-request isolation: the middleware sets these for the duration of one
# HTTP request and resets them in `finally`. Nothing credential-related is
# ever stored at module level.
_credentials_var: contextvars.ContextVar[AltPayCredentials | None] = contextvars.ContextVar(
    "altpay_credentials", default=None
)
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("altpay_request_id", default="-")

INSTRUCTIONS = (
    "Alternative Payments is a B2B payments platform for MSPs: the MSP (partner) "
    "bills its own customers through it, and customers pay invoices by card or "
    "ACH. Money collected is paid out to the MSP in payouts.\n"
    "Concepts: customer (an MSP client), invoice (amount owed, status UPCOMING/"
    "OVERDUE/RECEIVED/PAID/ARCHIVED), payment request (a standalone pay link), "
    "transaction (payment, refund or chargeback), payout, webhook subscription.\n"
    "Typical flows:\n"
    "- Who owes what: ap_list_invoices(status='OVERDUE') -> ap_get_invoice -> "
    "ap_get_invoice_payment_link to share a pay link.\n"
    "- Customer lookup: ap_list_customers -> ap_get_customer / ap_list_customer_users.\n"
    "- Reconciliation: ap_list_transactions (by customer, invoice, status, date) "
    "and ap_list_payouts -> ap_list_payout_transactions.\n"
    "- Webhooks: ap_list_webhooks, ap_list_webhook_events(status='failed') -> "
    "ap_retry_webhooks.\n"
    "Tools that create, archive or delete change real billing data: call them "
    "only when the user explicitly asks, with the exact values given. Lists "
    "return {items, has_more, next_cursor}; pass next_cursor as `after`."
)


def get_client_from_context() -> AltPayClient | None:
    """The client for the current request, or None outside a request."""
    credentials = _credentials_var.get()
    if credentials is None:
        return None
    return AltPayClient(credentials)


class GatewayCredentialsMiddleware:
    """Reads X-Alternative-Payments-* headers on /mcp requests into the request context.

    Missing required headers -> 401 listing them. An unknown environment does not block
    the request (tools/list must work with any values); tools report it instead.
    """

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope.get("path", "").startswith("/mcp"):
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        client_id = (request.headers.get(HEADER_CLIENT_ID) or "").strip()
        client_secret = (request.headers.get(HEADER_CLIENT_SECRET) or "").strip()
        environment = (request.headers.get(HEADER_ENVIRONMENT) or "").strip().lower() or DEFAULT_ENVIRONMENT

        missing = [h for h, v in ((HEADER_CLIENT_ID, client_id), (HEADER_CLIENT_SECRET, client_secret)) if not v]
        if missing:
            await JSONResponse(
                {
                    "error": "Missing credentials",
                    "message": "Required header(s) missing: " + ", ".join(missing),
                    "required_headers": REQUIRED_HEADERS,
                    "optional_headers": OPTIONAL_HEADERS,
                },
                status_code=401,
            )(scope, receive, send)
            return

        header_error = None
        if environment not in ENVIRONMENT_BASE_URLS:
            header_error = f"{HEADER_ENVIRONMENT} must be one of: {', '.join(ENVIRONMENT_BASE_URLS)}"
            environment = DEFAULT_ENVIRONMENT

        request_id = (request.headers.get("x-request-id") or "").strip()[:64] or uuid.uuid4().hex[:12]
        creds_token = _credentials_var.set(AltPayCredentials(client_id, client_secret, environment, header_error))
        rid_token = request_id_var.set(request_id)
        try:
            await self.app(scope, receive, send)
        finally:
            _credentials_var.reset(creds_token)
            request_id_var.reset(rid_token)


def create_mcp_server(settings: Settings | None = None) -> FastMCP:
    """Build the FastMCP server and register every tool."""
    mcp = FastMCP(
        name="alternative-payments-mcp",
        instructions=INSTRUCTIONS,
        # The service sits behind the gateway, so Host is never localhost;
        # DNS-rebinding protection would reject those requests with 421.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
        stateless_http=True,
    )

    client_factory: Callable[[], AltPayClient | None] = get_client_from_context

    from .tools import customers, invoicing, navigation, payments, webhooks

    for module in (navigation, customers, invoicing, payments, webhooks):
        module.register(mcp, client_factory)

    return mcp
