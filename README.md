# Alternative Payments MCP Server

An [MCP](https://modelcontextprotocol.io) server for the
[Alternative Payments](https://www.alternativepayments.io) partner API. It lets an AI agent
work with an MSP's billing in Alternative Payments: customers, invoices, standalone payment
requests, payment transactions, payouts and webhook subscriptions.

- Transport: MCP Streamable HTTP at `POST /mcp`, health probe at `GET /health`
- Stateless and multi-tenant: credentials arrive on every request as HTTP headers and are
  never stored; the OAuth access token is obtained per request and not cached
- Python 3.12, [uv](https://docs.astral.sh/uv/), FastMCP, httpx
- License: Apache-2.0, Copyright 2026 MSPbots.ai

<div align="center">

## MSPbots Connector

**The MCP Gateway built for MSPs: visible, controlled, and your data stays where it belongs.**

[**Get started at connect.mspbots.ai →**](https://connect.mspbots.ai)

</div>

---

MSPbots Connector gives your AI clients one MCP URL to reach your entire MSP stack (RMM, PSA, documentation, security, finance), and gives you control over who can call which tool and a record of everything that was called.

**Hosted service: [connect.mspbots.ai](https://connect.mspbots.ai)** · Free to use.

### Why Connector

![MSPbots Connector](https://stgoss.mspbots.ai/files/mcp/mspbots-mcp.png)

| | |
|---|---|
| **Visible** | Every tool call is logged: who, which vendor, when. Usage dashboard, CSV export, SIEM streaming. |
| **Controlled** | Role-based, per-tool allowlist. Deny by default. |
| **Protected** | Credentials encrypted per record. AI clients never see your vendor passwords or tokens. |
| **MSP-native** | Built for the MSP stack only: RMM, PSA, documentation, security, finance. |

### Quick start

1. **Sign up** at [connect.mspbots.ai](https://connect.mspbots.ai).
2. **Connect your vendors.** Pick from 150+ connectors and authorize each one on the vendor's own page, or bring your own API keys. No extra vendor accounts needed.
3. **Set access.** Create roles and decide which tools each role may call. Nothing is allowed until you allow it.
4. **Add your MCP URL to your AI client.** Copy the URL from your Connector dashboard into Claude, ChatGPT, Cursor, VS Code, Gemini, Codex, or any MCP-capable client.
5. **Ask your AI to do real work**, and watch every call appear in the audit log.

### Features

**Unified gateway**
- One MCP URL for all your AI clients
- 150+ connectors across the MSP stack
- Custom MCP servers supported, free
- Authorization happens on each vendor's own page; the AI never sees passwords or tokens
- Bring your own credentials: use the vendor API keys you already have
- Multiple accounts per app; connect once, reuse across AI clients
- Tool search: finds the right action for the task
- One sign-in; vendor credentials are injected behind the scenes and OAuth tokens refresh automatically

**Visibility**
- Audit log for every tool call (who, which vendor, when)
- Usage dashboard: call volume, top vendors, error rate, per-user activity
- Export audit logs to CSV, or stream to Loki, Graylog, or LogScale (SIEM)
- Optional recording of tool arguments and result summaries (off by default, enabled per organization)

**Control**
- Per-role, per-tool allowlist, deny by default
- owner / admin / member roles
- SCIM provisioning with Entra ID, Okta, JumpCloud, and Google Workspace

**Security**
- Credentials encrypted one record at a time (AES-256-GCM, per-record key)
- AI clients authenticate with OAuth 2.1 + PKCE
- Vendor responses are scanned for prompt-injection patterns and returned as structured data. This is one layer of defense, not a guarantee against every attack.
- Static egress IP for customer firewall and API allowlisting

### Pricing

**Free.**

Links: [connect.mspbots.ai](https://connect.mspbots.ai) · [mspbots.ai](https://mspbots.ai)

---

## Authentication headers

| Header | Required | Type | Default | Allowed values | Description | Example |
|---|---|---|---|---|---|---|
| `X-Alternative-Payments-Client-Id` | Yes | string | none | - | API key client id | `your-client-id` |
| `X-Alternative-Payments-Client-Secret` | Yes | string | none | - | Client secret paired with the client id | `your-client-secret` |
| `X-Alternative-Payments-Environment` | No | string | `production` | `production`, `demo` | `production` uses `public-api.alternativepayments.io`; `demo` uses `public-api.demo.alternativepayments.io` | `production` |

Where to get them:

- **Client id / secret**: in the Alternative Payments Partner Dashboard open
  **Team Preferences -> API Keys -> Generate API Key**. The server exchanges them for a
  short-lived bearer token (OAuth 2.0 client credentials) on each request; the secret is only
  sent to the token endpoint.
- **Scopes**: pick read scopes for Customers, Invoices, Payments, Payouts and Webhooks for the
  read tools. Add the matching write scopes only if the agent should create or archive
  customers/invoices, create payment requests, or manage webhooks.
- **Environment**: use `demo` for a sandbox API key.

A request to `/mcp` without the required headers gets HTTP 401 with the list of required
headers; an unknown environment does not block the request, and tools return
`invalid_argument` instead.

## Tools

All tools return a JSON string. List tools return `{items, count, has_more, next_cursor}`;
pass `next_cursor` as `after` to get the next page. `limit` defaults to 50 (max 100).
Amounts are in US dollars; USD is the only supported currency.

Read tools:

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `ap_navigate` | Show the tools of one area | **domain** (`customers`, `invoicing`, `payments`, `webhooks`) |
| `ap_status` | Check the credentials and environment | - |
| `ap_list_customers` | List customers | limit, after, company_name |
| `ap_get_customer` | One customer | **id** |
| `ap_list_customer_users` | Portal users of a customer | **id**, limit, after |
| `ap_list_invoices` | List invoices | status (`UPCOMING`, `OVERDUE`, `RECEIVED`, `PAID`, `ARCHIVED`), customer_id, limit, after, invoice_number, due_date_start, due_date_end |
| `ap_get_invoice` | One invoice | **id** |
| `ap_get_invoice_payment_link` | Hosted pay link for an invoice | **id** |
| `ap_get_invoice_pdf_link` | PDF download link for an invoice | **id** |
| `ap_get_payment_request` | One payment request | **id** |
| `ap_list_transactions` | Payments, refunds, chargebacks | limit, after, before, type, status, customer_id, invoice_id, payment_method, created_at_start, created_at_end |
| `ap_get_transaction` | One transaction | **id** |
| `ap_list_payouts` | Payouts to the MSP | limit, after, status, start_date, end_date |
| `ap_get_payout` | One payout | **id** |
| `ap_list_payout_transactions` | Transactions inside a payout | **id** |
| `ap_list_webhooks` | Webhook subscriptions | limit, topic, after |
| `ap_list_webhook_events` | Webhook deliveries | limit, status (`pending`, `sent`, `failed`), topic, after |

Write tools (**change real billing data**; descriptions tell the agent to call them only when
the user explicitly asks):

| Tool | Purpose | Parameters (required in **bold**) |
|---|---|---|
| `ap_create_customer` | Create a customer | **name**, **email**, legal_name, external_id, street_address, city, state, postal_code, country |
| `ap_add_customer_user` | Add a portal user to a customer | **id**, **email**, **first_name**, **last_name** |
| `ap_archive_customer` | Archive a customer (destructive) | **id** |
| `ap_create_invoice` | Create an invoice | **customer_id**, **currency** (`USD`), **due_date** (`YYYY-MM-DD`), **line_items** (`[{description, amount, quantity}]`) |
| `ap_create_payment_request` | Create a standalone pay link | **amount**, **currency** (`USD`), **redirect_url** (https), reference_id |
| `ap_archive_invoice` | Archive an invoice (destructive) | **id** |
| `ap_create_webhook` | Subscribe an https endpoint to a topic | **endpoint_url**, **topic**, secret_key |
| `ap_retry_webhooks` | Re-send failed webhook deliveries | - |
| `ap_delete_webhook` | Delete a subscription (destructive) | **subscription_id** |

Errors come back as a JSON envelope instead of an exception:

```json
{"error": {"code": "unauthorized", "message": "Alternative Payments rejected the client id / secret (token request failed)", "retryable": false}}
```

`code` is one of `not_configured`, `unauthorized`, `not_found`, `invalid_argument`,
`rate_limited`, `upstream_error`.

## Run locally

```bash
uv sync
uv run python -m alternative_payments_mcp          # listens on 0.0.0.0:8080
```

or with Docker:

```bash
docker build --platform linux/amd64 -t alternative-payments-mcp:dev .
docker run --rm -p 8080:8080 alternative-payments-mcp:dev
```

Configuration (environment variables, all optional): `MCP_HTTP_HOST` (default `0.0.0.0`),
`MCP_HTTP_PORT` (default `8080`), `LOG_LEVEL` (default `INFO`). Credentials are never read from
the environment.

## Testing example

```bash
# list tools
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Alternative-Payments-Client-Id: your-client-id" \
  -H "X-Alternative-Payments-Client-Secret: your-client-secret" \
  -H "X-Alternative-Payments-Environment: demo" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}'

# overdue invoices
curl -s http://localhost:8080/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "X-Alternative-Payments-Client-Id: your-client-id" \
  -H "X-Alternative-Payments-Client-Secret: your-client-secret" \
  -H "X-Alternative-Payments-Environment: demo" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"ap_list_invoices","arguments":{"status":"OVERDUE","limit":10}}}'
```

Unit tests (no network access needed):

```bash
uv run pytest
```

## Delivery notes

- **Tool count (26).** Above the suggested 20 because the tool names are an existing contract
  used by agents and tenant connections; none were merged or removed. The `ap_` prefix is also
  kept for the same reason.
- **Write tools.** Nine tools change data. They are annotated (`readOnlyHint=false`; archive and
  delete also `destructiveHint=true`), validate their input before calling the API
  (USD only, `YYYY-MM-DD` dates, https URLs), and their descriptions tell the agent to act only
  on an explicit request.
- **Currency.** The partner API bills in USD only. `ap_create_payment_request` keeps its
  `currency` argument for compatibility and rejects anything other than `USD`.

## License

Apache License 2.0 - see [LICENSE](LICENSE) and [NOTICE](NOTICE).
