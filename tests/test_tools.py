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
"""tools/list snapshot and error-envelope mapping. No network access."""

import asyncio
import json

import pytest

from alternative_payments_mcp.api_client import AltPayError
from alternative_payments_mcp.server import INSTRUCTIONS, create_mcp_server

# Tool names are a public contract: existing agents and tenant connections
# depend on them. Changing this snapshot is a breaking change.
EXPECTED_TOOLS: dict[str, set[str]] = {
    "ap_navigate": {"domain"},
    "ap_status": set(),
    "ap_list_customers": set(),
    "ap_get_customer": {"id"},
    "ap_list_customer_users": {"id"},
    "ap_create_customer": {"name", "email"},
    "ap_add_customer_user": {"id", "email", "first_name", "last_name"},
    "ap_archive_customer": {"id"},
    "ap_list_invoices": set(),
    "ap_get_invoice": {"id"},
    "ap_get_invoice_payment_link": {"id"},
    "ap_get_invoice_pdf_link": {"id"},
    "ap_create_invoice": {"customer_id", "currency", "due_date", "line_items"},
    "ap_create_payment_request": {"amount", "currency", "redirect_url"},
    "ap_get_payment_request": {"id"},
    "ap_archive_invoice": {"id"},
    "ap_list_transactions": set(),
    "ap_get_transaction": {"id"},
    "ap_list_payouts": set(),
    "ap_get_payout": {"id"},
    "ap_list_payout_transactions": {"id"},
    "ap_list_webhooks": set(),
    "ap_list_webhook_events": set(),
    "ap_create_webhook": {"endpoint_url", "topic"},
    "ap_retry_webhooks": set(),
    "ap_delete_webhook": {"subscription_id"},
}

WRITE_TOOLS = {
    "ap_create_customer",
    "ap_add_customer_user",
    "ap_archive_customer",
    "ap_create_invoice",
    "ap_create_payment_request",
    "ap_archive_invoice",
    "ap_create_webhook",
    "ap_retry_webhooks",
    "ap_delete_webhook",
}
DESTRUCTIVE_TOOLS = {"ap_archive_customer", "ap_archive_invoice", "ap_delete_webhook"}


@pytest.fixture(scope="module")
def tools():
    return {t.name: t for t in asyncio.run(create_mcp_server().list_tools())}


def test_tool_names_snapshot(tools):
    assert set(tools) == set(EXPECTED_TOOLS)


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_required_params(tools, name):
    assert set(tools[name].inputSchema.get("required", [])) == EXPECTED_TOOLS[name]


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_description_budget(tools, name):
    description = (tools[name].description or "").strip()
    assert description, f"{name} has no description"
    assert len(description) <= 500
    assert len(description.splitlines()[0]) <= 100
    assert "API:" not in description


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_every_param_is_documented(tools, name):
    for param, schema in tools[name].inputSchema.get("properties", {}).items():
        assert schema.get("description") or "enum" in json.dumps(schema), f"{name}.{param}"


@pytest.mark.parametrize("name", sorted(EXPECTED_TOOLS))
def test_annotations(tools, name):
    annotations = tools[name].annotations
    assert annotations is not None
    assert annotations.readOnlyHint is (name not in WRITE_TOOLS)
    assert bool(annotations.destructiveHint) is (name in DESTRUCTIVE_TOOLS)


@pytest.mark.parametrize("name", sorted(WRITE_TOOLS - {"ap_retry_webhooks"}))
def test_write_tools_warn_the_agent(tools, name):
    assert "explicitly asks" in tools[name].description


def test_instructions_present_and_bounded():
    assert INSTRUCTIONS and len(INSTRUCTIONS) <= 1500
    for name in ("ap_list_invoices", "ap_list_transactions", "ap_list_payouts"):
        assert name in INSTRUCTIONS


def test_navigate_covers_every_tool():
    from alternative_payments_mcp.tools.navigation import DOMAIN_TOOLS

    listed = {tool for tools_ in DOMAIN_TOOLS.values() for tool in tools_}
    assert listed == set(EXPECTED_TOOLS) - {"ap_navigate", "ap_status"}


@pytest.mark.parametrize(
    "status_code,expected_code,expected_retryable",
    [
        (0, "upstream_error", True),
        (400, "invalid_argument", False),
        (401, "unauthorized", False),
        (403, "unauthorized", False),
        (404, "not_found", False),
        (422, "invalid_argument", False),
        (429, "rate_limited", True),
        (500, "upstream_error", True),
        (503, "upstream_error", True),
    ],
)
def test_error_envelope_mapping(status_code, expected_code, expected_retryable):
    envelope = json.loads(AltPayError(status_code, "boom").to_envelope())
    assert envelope == {
        "error": {"code": expected_code, "message": "boom", "retryable": expected_retryable}
    }
