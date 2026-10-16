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
"""Customers (the MSP's own clients) and their portal users."""

from typing import Annotated, Any

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from ..api_client import AltPayClient
from ._common import (
    CREATES,
    READ_ONLY,
    REMOVES,
    After,
    ClientFactory,
    Limit,
    list_result,
    page_params,
    path_id,
    run_tool,
    unwrap,
)

CustomerId = Annotated[str, Field(description="Customer id from ap_list_customers.")]
Optional = Annotated[str | None, Field(description="Optional.")]


def register(mcp: FastMCP, client_factory: ClientFactory) -> None:
    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_customers(
        limit: Limit = None,
        after: After = None,
        company_name: Annotated[str | None, Field(description="Filter by company name.")] = None,
    ) -> str:
        """List customers (the MSP's clients billed through Alternative Payments)."""

        async def action(client: AltPayClient) -> dict:
            params = page_params(limit, after) | {"company_name": company_name}
            return list_result(await client.get("/customers", params))

        return await run_tool("ap_list_customers", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_get_customer(id: CustomerId) -> str:
        """Get one customer: name, legal name, e-mail, address, external id."""

        async def action(client: AltPayClient) -> Any:
            return unwrap(await client.get(f"/customers/{path_id(id)}"))

        return await run_tool("ap_get_customer", client_factory, action)

    @mcp.tool(annotations=READ_ONLY)
    async def ap_list_customer_users(id: CustomerId, limit: Limit = None, after: After = None) -> str:
        """List the portal users of one customer (people who can view and pay its invoices)."""

        async def action(client: AltPayClient) -> dict:
            return list_result(await client.get(f"/customers/{path_id(id)}/users", page_params(limit, after)))

        return await run_tool("ap_list_customer_users", client_factory, action)

    @mcp.tool(annotations=CREATES)
    async def ap_create_customer(
        name: Annotated[str, Field(description="Customer (company) name.")],
        email: Annotated[str, Field(description="Billing e-mail address.")],
        legal_name: Optional = None,
        external_id: Annotated[str | None, Field(description="Your own id for this customer, e.g. PSA company id.")] = None,
        street_address: Optional = None,
        city: Optional = None,
        state: Optional = None,
        postal_code: Optional = None,
        country: Optional = None,
    ) -> str:
        """Create a customer. Changes billing data: only when the user explicitly asks."""

        async def action(client: AltPayClient) -> Any:
            body = {
                k: v
                for k, v in {
                    "name": name,
                    "email": email,
                    "legal_name": legal_name,
                    "external_id": external_id,
                    "street_address": street_address,
                    "city": city,
                    "state": state,
                    "postal_code": postal_code,
                    "country": country,
                }.items()
                if v is not None
            }
            return unwrap(await client.post("/customers", body=body))

        return await run_tool("ap_create_customer", client_factory, action)

    @mcp.tool(annotations=CREATES)
    async def ap_add_customer_user(
        id: CustomerId,
        email: Annotated[str, Field(description="User e-mail address.")],
        first_name: Annotated[str, Field(description="First name.")],
        last_name: Annotated[str, Field(description="Last name.")],
    ) -> str:
        """Add a portal user to a customer. Changes data: only when the user explicitly asks."""

        async def action(client: AltPayClient) -> Any:
            body = {"email": email, "first_name": first_name, "last_name": last_name}
            return unwrap(await client.post(f"/customers/{path_id(id)}/users", body=body))

        return await run_tool("ap_add_customer_user", client_factory, action)

    @mcp.tool(annotations=REMOVES)
    async def ap_archive_customer(id: CustomerId) -> str:
        """Archive one customer so it can no longer be billed.

        Destructive: only when the user explicitly asks to archive that customer id.
        """

        async def action(client: AltPayClient) -> Any:
            result = unwrap(await client.request("DELETE", f"/customers/{path_id(id)}"))
            return {"archived": True, "id": id, **(result if isinstance(result, dict) else {})}

        return await run_tool("ap_archive_customer", client_factory, action)
