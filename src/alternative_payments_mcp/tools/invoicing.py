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
"""Invoices and standalone payment requests."""

import re
from typing import Annotated, Any, Literal

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

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

InvoiceId = Annotated[str, Field(description="Invoice id from ap_list_invoices.")]
DateArg = Annotated[str | None, Field(description="Date, YYYY-MM-DD.")]
InvoiceStatus = Literal["UPCOMING", "OVERDUE", "RECEIVED", "PAID", "ARCHIVED"]

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class LineItem(BaseModel):
    description: str = Field(description="What is being billed.")
    amount: float = Field(description="Unit price in dollars, e.g. 125.50.")
    quantity: int | None = Field(default=None, description="Quantity (default 1).")


def _usd(currency: str) -> str:
    if currency.strip().upper() != "USD":
        raise ValueError("Alternative Payments only supports currency USD")
    return "USD"


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_invoices(
        status: Annotated[InvoiceStatus | str | None, Field(description="Invoice status.")] = None,
        customer_id: Annotated[str | None, Field(description="Only this customer's invoices.")] = None,
        limit: Limit = None,
        after: After = None,
        invoice_number: Annotated[str | None, Field(description="Exact invoice number.")] = None,
        due_date_start: DateArg = None,
        due_date_end: DateArg = None,
    ) -> str:
        """List invoices with amount, due date and status; filter by status, customer or due date."""

        async def action(client: AltPayClient) -> dict:
            params = page_params(limit, after) | {
                "status": enum_value(status, InvoiceStatus),
                "customer_id": customer_id,
                "invoice_number": invoice_number,
                "due_date_start": due_date_start,
                "due_date_end": due_date_end,
            }
            return list_result(await client.get("/invoices", params))

        return await run_tool("ap_list_invoices", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_invoice(id: InvoiceId) -> str:
        """Get one invoice: customer, line items, amounts, due date, status, payments."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/invoices/{path_id(id)}"))

        return await run_tool("ap_get_invoice", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_invoice_payment_link(id: InvoiceId) -> str:
        """Get the hosted payment page link for an invoice, to send to the customer."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/invoices/{path_id(id)}/payment-link"))

        return await run_tool("ap_get_invoice_payment_link", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_invoice_pdf_link(id: InvoiceId) -> str:
        """Get a download link for an invoice's PDF."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/invoices/{path_id(id)}/pdf-link"))

        return await run_tool("ap_get_invoice_pdf_link", client_factory, action)

    @mcp.tool(annotations=CREATES)
    async def ap_create_invoice(
        customer_id: Annotated[str, Field(description="Customer to bill (from ap_list_customers).")],
        currency: Annotated[str, Field(description="Currency; only USD is supported.")],
        due_date: Annotated[str, Field(description="Due date, YYYY-MM-DD.")],
        line_items: Annotated[list[LineItem], Field(description="At least one line item.", min_length=1)],
    ) -> str:
        """Create an invoice for a customer. Bills a real customer: only when the user explicitly asks."""

        async def action(client: AltPayClient) -> Any:
            if not _DATE_RE.match(due_date.strip()):
                raise ValueError("due_date must be YYYY-MM-DD")
            body = {
                "customer_id": customer_id,
                "currency": _usd(currency),
                "due_date": due_date.strip(),
                "line_items": [item.model_dump(exclude_none=True) for item in line_items],
            }
            return unwrap(await client.post("/invoices", body=body))

        return await run_tool("ap_create_invoice", client_factory, action)

    @mcp.tool(annotations=CREATES)
    async def ap_create_payment_request(
        amount: Annotated[float, Field(description="Amount in dollars, e.g. 250.00.", gt=0)],
        currency: Annotated[str, Field(description="Currency; only USD is supported.")],
        redirect_url: Annotated[str, Field(description="Where the payer is sent after paying (https URL).")],
        reference_id: Annotated[str | None, Field(description="Your own reference for this request.")] = None,
    ) -> str:
        """Create a standalone payment request (pay link) not tied to an invoice.

        Creates a real request for money: only when the user explicitly asks.
        """

        async def action(client: AltPayClient) -> Any:
            _usd(currency)
            if not redirect_url.strip().lower().startswith("https://"):
                raise ValueError("redirect_url must be an https URL")
            body = {"amount": f"{amount:.2f}", "redirect_url": redirect_url.strip()}
            if reference_id:
                body["reference_id"] = reference_id
            return unwrap(await client.post("/payments/request", body=body))

        return await run_tool("ap_create_payment_request", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_payment_request(
        id: Annotated[str, Field(description="Payment request id.")],
    ) -> str:
        """Get one payment request: amount, pay link and status."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/payments/request/{path_id(id)}"))

        return await run_tool("ap_get_payment_request", client_factory, action)

    @mcp.tool(annotations=REMOVES)
    async def ap_archive_invoice(id: InvoiceId) -> str:
        """Archive one invoice so it is no longer payable.

        Destructive: only when the user explicitly asks to archive that invoice id.
        """

        async def action(client: AltPayClient) -> Any:
            result = unwrap(await client.request("DELETE", f"/invoices/{path_id(id)}"))
            return {"archived": True, "id": id, **(result if isinstance(result, dict) else {})}

        return await run_tool("ap_archive_invoice", client_factory, action)
