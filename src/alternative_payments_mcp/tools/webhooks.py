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
"""Webhook subscriptions and delivery events."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import Field

from ..api_client import AltPayClient
from ._common import (
    CREATES,
    READ_ONLY,
    REMOVES,
    After,
    ClientFactory,
    Limit,
    enum_value,
    list_result,
    page_params,
    path_id,
    run_tool,
    unwrap,
)

Topic = Literal[
    "payout_paid",
    "payout_failed",
    "payout_processing",
    "payout_scheduled",
    "customer_created",
    "customer_updated",
    "customer_archived",
    "payment_succeeded",
    "payment_chargeback",
    "payment_refunded",
    "invoice_paid",
    "invoice_archived",
    "invoice_created",
    "invoice_updated",
    "payment_failed",
    "payment_method_added",
    "payment_method_deleted",
    "default_payment_method_changed",
]
EventStatus = Literal["pending", "sent", "failed"]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_webhooks(
        limit: Limit = None,
        topic: Annotated[Topic | str | None, Field(description="Event topic.")] = None,
        after: After = None,
    ) -> str:
        """List webhook subscriptions: id, topic, endpoint URL and whether it is active."""

        async def action(client: AltPayClient) -> dict:
            return list_result(await client.get("/webhooks", page_params(limit, after) | {"topic": enum_value(topic, Topic)}))

        return await run_tool("ap_list_webhooks", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_webhook_events(
        limit: Limit = None,
        status: Annotated[EventStatus | str | None, Field(description="Delivery status.")] = None,
        topic: Annotated[Topic | str | None, Field(description="Event topic.")] = None,
        after: After = None,
    ) -> str:
        """List webhook delivery events; status=failed shows deliveries that need a retry."""

        async def action(client: AltPayClient) -> dict:
            params = page_params(limit, after) | {"status": enum_value(status, EventStatus), "topic": enum_value(topic, Topic)}
            return list_result(await client.get("/webhooks/events", params))

        return await run_tool("ap_list_webhook_events", client_factory, action)

    @mcp.tool(annotations=CREATES)
    async def ap_create_webhook(
        endpoint_url: Annotated[str, Field(description="HTTPS URL that will receive the events.")],
        topic: Annotated[Topic | str, Field(description="Event topic to subscribe to.")],
        secret_key: Annotated[
            str | None, Field(description="Optional shared secret used to sign deliveries.")
        ] = None,
    ) -> str:
        """Subscribe an HTTPS endpoint to one event topic. Only when the user explicitly asks."""

        async def action(client: AltPayClient) -> Any:
            if not endpoint_url.strip().lower().startswith("https://"):
                raise ValueError("endpoint_url must be an https URL")
            body = {"endpoint_url": endpoint_url.strip(), "topic": enum_value(topic, Topic)}
            if secret_key:
                body["secret_key"] = secret_key
            return unwrap(await client.post("/webhooks", body=body))

        return await run_tool("ap_create_webhook", client_factory, action)

    @mcp.tool(
        annotations=ToolAnnotations(
            readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True
        )
    )
    async def ap_retry_webhooks() -> str:
        """Re-send all failed webhook deliveries.

        Re-sends every failed delivery at once; only when the user explicitly asks.
        """

        async def action(client: AltPayClient) -> Any:
            result = unwrap(await client.post("/webhooks/retry"))
            return result if isinstance(result, dict) else {"retried": True}

        return await run_tool("ap_retry_webhooks", client_factory, action)

    @mcp.tool(annotations=REMOVES)
    async def ap_delete_webhook(
        subscription_id: Annotated[str, Field(description="Subscription id from ap_list_webhooks.")],
    ) -> str:
        """Delete one webhook subscription; its endpoint stops receiving events.

        Destructive: only when the user explicitly asks to delete that subscription id.
        """

        async def action(client: AltPayClient) -> Any:
            await client.request("DELETE", f"/webhooks/{path_id(subscription_id)}")
            return {"deleted": True, "subscription_id": subscription_id}

        return await run_tool("ap_delete_webhook", client_factory, action)
