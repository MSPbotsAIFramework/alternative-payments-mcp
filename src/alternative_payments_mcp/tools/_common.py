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
"""Shared argument types, result shaping and the error-handling wrapper."""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Annotated, Any, get_args
from urllib.parse import quote

from mcp.types import ToolAnnotations
from pydantic import Field

from .._json import dump_json_capped, error_envelope
from ..api_client import AltPayClient, AltPayError

logger = logging.getLogger("alternative_payments_mcp.tools")

ClientFactory = Callable[[], AltPayClient | None]

DEFAULT_LIMIT = 50
MAX_LIMIT = 100  # the API's own default page size

READ_ONLY = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
CREATES = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True)
REMOVES = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True)

NOT_CONFIGURED = error_envelope(
    "not_configured",
    "Alternative Payments credentials are missing for this request "
    "(X-Alternative-Payments-Client-Id / X-Alternative-Payments-Client-Secret).",
    False,
)

Limit = Annotated[int | None, Field(description=f"Max items (default {DEFAULT_LIMIT}, max {MAX_LIMIT}).")]
After = Annotated[str | None, Field(description="Cursor: next_cursor from a previous call, for the next page.")]


def page_params(limit: int | None, after: str | None = None) -> dict[str, Any]:
    size = DEFAULT_LIMIT if limit is None else max(1, min(int(limit), MAX_LIMIT))
    params: dict[str, Any] = {"limit": size}
    if after:
        params["after"] = after
    return params


def list_result(document: Any) -> dict[str, Any]:
    """Shape a cursor page ``{data, end_cursor, has_next_page}`` as ``{items, count, has_more, next_cursor}``."""
    if isinstance(document, list):
        return {"items": document, "count": len(document), "has_more": False, "next_cursor": None}
    doc = document if isinstance(document, dict) else {}
    items = doc.get("data") or []
    has_more = bool(doc.get("has_next_page"))
    return {
        "items": items,
        "count": len(items),
        "has_more": has_more,
        "next_cursor": doc.get("end_cursor") if has_more else None,
    }


def unwrap(document: Any) -> Any:
    """Single-object responses may be wrapped as ``{data: {...}}``."""
    if isinstance(document, dict) and set(document) == {"data"} and isinstance(document["data"], dict):
        return document["data"]
    return document


def path_id(value: Any) -> str:
    """Percent-encode an ID for use as a single URL path segment."""
    return quote(str(value).strip(), safe="")


def enum_value(value: Any, choices: Any) -> Any:
    """Canonical spelling of a case-insensitive match in ``choices`` (a Literal type).

    Any other value passes through unchanged, so the API decides (older callers sent free text).
    """
    if not isinstance(value, str):
        return value
    wanted = value.strip().lower()
    return next((c for c in get_args(choices) if isinstance(c, str) and c.lower() == wanted), value)


async def run_tool(
    name: str,
    client_factory: ClientFactory,
    action: Callable[[AltPayClient], Awaitable[Any]],
) -> str:
    """Resolve the caller's client, run ``action``, and always return a string.

    Errors never escape as exceptions: they become the standard error envelope.
    """
    client = client_factory()
    if client is None:
        return NOT_CONFIGURED
    if client.header_error:
        return error_envelope("invalid_argument", client.header_error, False)
    started = time.monotonic()
    try:
        result = await action(client)
    except AltPayError as e:
        logger.info("tool=%s outcome=error status=%s ms=%d", name, e.status_code, _ms(started))
        return e.to_envelope()
    except ValueError as e:
        logger.info("tool=%s outcome=invalid_argument ms=%d", name, _ms(started))
        return error_envelope("invalid_argument", str(e), False)
    except Exception as e:  # noqa: BLE001 - tools must never raise
        logger.warning("tool=%s outcome=unexpected error=%s ms=%d", name, type(e).__name__, _ms(started))
        return error_envelope("upstream_error", f"Unexpected error: {type(e).__name__}", True)
    logger.info("tool=%s outcome=ok ms=%d", name, _ms(started))
    return result if isinstance(result, str) else dump_json_capped(result)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)
