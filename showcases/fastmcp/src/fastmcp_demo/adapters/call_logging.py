"""Host-owned middleware that logs every tool call.

A sibling of :mod:`fastmcp_demo.adapters.tracing`: tracing opens spans, this
writes a log line. It is deliberately independent of OpenTelemetry so tool calls
are observable even when tracing is disabled (the test default).

Each call logs the tool name and a truncated preview of its arguments at
``INFO`` on the way in, and the outcome (``ok``/``error`` plus elapsed time) on
the way out. The caller-provided MCP ``request_id`` ties the two lines together.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext
    from mcp.types import CallToolRequestParams

logger = logging.getLogger(__name__)

#: Longest argument preview logged; keeps a log line on one readable line.
_MAX_ARGUMENT_CHARS = 200


def _preview(arguments: Any) -> str:
    """Render *arguments* as a single-line, length-capped string."""
    text = repr(arguments)
    if len(text) > _MAX_ARGUMENT_CHARS:
        return f"{text[:_MAX_ARGUMENT_CHARS]}…"
    return text


def _requested_version(message: Any) -> str:
    """The version a caller negotiated, or ``"latest"`` when unspecified.

    FastMCP routes a versioned call using the reserved ``_meta.fastmcp.version``
    entry; when absent the server serves the highest version, so the log reads
    ``latest`` rather than claiming a concrete one.
    """
    meta = getattr(message, "meta", None)
    if not isinstance(meta, dict):
        return "latest"
    fastmcp = meta.get("fastmcp")
    if not isinstance(fastmcp, dict):
        return "latest"
    version = fastmcp.get("version")
    if isinstance(version, str):
        return version
    if isinstance(version, dict):
        return version.get("eq") or f">={version.get('gte')}<{version.get('lt')}"
    return "latest"


class CallLoggingMiddleware(Middleware):
    """Log the tool name, its arguments, and the call outcome.

    Mirrors :class:`~fastmcp_demo.adapters.tracing.CallSpanMiddleware` but emits
    logs instead of spans, so it stays useful when tracing is off.
    """

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ) -> Any:
        message = context.message
        kind = message.name
        version = _requested_version(message)
        logger.info(
            "tool call: %s version=%s args=%s",
            kind,
            version,
            _preview(message.arguments),
        )
        started = time.perf_counter()
        try:
            result = await call_next(context)
        except Exception:
            logger.exception(
                "tool call failed: %s version=%s after %.1f ms",
                kind,
                version,
                (time.perf_counter() - started) * 1000,
            )
            raise
        logger.info(
            "tool call ok: %s version=%s in %.1f ms",
            kind,
            version,
            (time.perf_counter() - started) * 1000,
        )
        return result


__all__ = ["CallLoggingMiddleware"]
