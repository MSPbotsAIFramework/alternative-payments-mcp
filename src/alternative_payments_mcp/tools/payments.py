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
"""Transactions (payments, refunds, chargebacks) and payouts to the MSP."""

from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AltPayClient
from ._common import READ_ONLY, After, ClientFactory, Limit, list_result, page_params, path_id, run_tool, unwrap

Timestamp = Annotated[str | None, Field(description="RFC 3339 timestamp, e.g. 2026-01-31T00:00:00Z.")]
PayoutId = Annotated[str, Field(description="Payout id from ap_list_payouts.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_transactions(
        limit: Limit = None,
        after: After = None,
        before: Annotated[str | None, Field(description="Cursor for the previous page.")] = None,
        type: Annotated[
            Literal["payment", "refund", "chargeback"] | None, Field(description="Transaction type.")
        ] = None,
        status: Annotated[
            Literal["creating", "processing", "scheduled", "succeeded", "canceled", "failed", "pending"] | None,
            Field(description="Transaction status."),
        ] = None,
        customer_id: Annotated[str | None, Field(description="Only this customer.")] = None,
        invoice_id: Annotated[str | None, Field(description="Only this invoice.")] = None,
        payment_method: Annotated[
            Literal["card", "standard_ach", "same_day_ach", "manual"] | None, Field(description="Payment method.")
        ] = None,
        created_at_start: Timestamp = None,
        created_at_end: Timestamp = None,
    ) -> str:
        """List payment transactions (payments, refunds, chargebacks) with amount, status and method.

        Use for reconciliation by customer, invoice, status or date range.
        """

        async def action(client: AltPayClient) -> dict:
            params = page_params(limit, after) | {
                "before": before,
                "type": type,
                "status": status,
                "customer_id": customer_id,
                "invoice_id": invoice_id,
                "payment_method": payment_method,
                "created_at_start": created_at_start,
                "created_at_end": created_at_end,
            }
            return list_result(await client.get("/payments", params))

        return await run_tool("ap_list_transactions", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_transaction(
        id: Annotated[str, Field(description="Transaction id from ap_list_transactions.")],
    ) -> str:
        """Get one transaction: amount, fees, status, method, customer and invoice."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/payments/{path_id(id)}"))

        return await run_tool("ap_get_transaction", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_payouts(
        limit: Limit = None,
        after: After = None,
        status: Annotated[
            Literal[
                "creating", "processing", "analyzing", "succeeded", "scheduled", "approved", "canceled", "pending", "failed"
            ]
            | None,
            Field(description="Payout status."),
        ] = None,
        start_date: Annotated[str | None, Field(description="From date, YYYY-MM-DD.")] = None,
        end_date: Annotated[str | None, Field(description="To date, YYYY-MM-DD.")] = None,
    ) -> str:
        """List payouts of collected funds to the MSP's bank account, with amount, date and status."""

        async def action(client: AltPayClient) -> dict:
            params = page_params(limit, after) | {"status": status, "start_date": start_date, "end_date": end_date}
            return list_result(await client.get("/payouts", params))

        return await run_tool("ap_list_payouts", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_payout(id: PayoutId) -> str:
        """Get one payout: amount, fees, arrival date and status."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/payouts/{path_id(id)}"))

        return await run_tool("ap_get_payout", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_payout_transactions(id: PayoutId) -> str:
        """List the transactions included in one payout, to reconcile a bank deposit."""

        async def action(client: AltPayClient) -> dict:
            return list_result(await client.get(f"/payouts/{path_id(id)}/transactions"))

        return await run_tool("ap_list_payout_transactions", client_factory, action)
