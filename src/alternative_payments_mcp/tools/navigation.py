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
"""Credential check and a per-area tool guide."""

from typing import Annotated, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AltPayClient
from ._common import READ_ONLY, ClientFactory, run_tool

DOMAIN_TOOLS: dict[str, dict[str, str]] = {
    "customers": {
        "ap_list_customers": "List customers.",
        "ap_get_customer": "One customer.",
        "ap_list_customer_users": "Portal users of a customer.",
        "ap_create_customer": "Create a customer (write).",
        "ap_add_customer_user": "Add a portal user (write).",
        "ap_archive_customer": "Archive a customer (destructive).",
    },
    "invoicing": {
        "ap_list_invoices": "List invoices by status, customer or due date.",
        "ap_get_invoice": "One invoice.",
        "ap_get_invoice_payment_link": "Hosted pay link of an invoice.",
        "ap_get_invoice_pdf_link": "PDF link of an invoice.",
        "ap_create_invoice": "Create an invoice (write).",
        "ap_create_payment_request": "Create a standalone pay link (write).",
        "ap_get_payment_request": "One payment request.",
        "ap_archive_invoice": "Archive an invoice (destructive).",
    },
    "payments": {
        "ap_list_transactions": "Payments, refunds and chargebacks.",
        "ap_get_transaction": "One transaction.",
        "ap_list_payouts": "Payouts to the MSP.",
        "ap_get_payout": "One payout.",
        "ap_list_payout_transactions": "Transactions inside a payout.",
    },
    "webhooks": {
        "ap_list_webhooks": "Webhook subscriptions.",
        "ap_list_webhook_events": "Webhook deliveries.",
        "ap_create_webhook": "Subscribe an endpoint (write).",
        "ap_retry_webhooks": "Re-send failed deliveries.",
        "ap_delete_webhook": "Delete a subscription (destructive).",
    },
}


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def ap_navigate(
        domain: Annotated[
            Literal["customers", "invoicing", "payments", "webhooks"],
            Field(description="Area to show tools for."),
        ],
    ) -> str:
        """Show which tools cover one area: customers, invoicing, payments or webhooks.

        All tools are always available; this is only a guide. Makes no API call.
        """

        async def action(_client: AltPayClient) -> dict:
            return {"domain": domain, "tools": DOMAIN_TOOLS[domain]}

        return await run_tool("ap_navigate", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_status() -> str:
        """Check that the Alternative Payments credentials work and which environment is used.

        Use it to diagnose unauthorized errors from other tools.
        """

        async def action(client: AltPayClient) -> dict:
            await client.get("/customers", {"limit": 1})
            return {"authenticated": True, "environment": client.environment, "api_base_url": client.base_url}

        return await run_tool("ap_status", client_factory, action)
