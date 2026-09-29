from __future__ import annotations

from typing import TYPE_CHECKING

from fastmcp.server.middleware import Middleware
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext


class ConvergeMiddleware(Middleware):
    """Converge the versioned models embedded in a tool call's arguments.

    Version negotiation is FastMCP's own: a call's ``version=`` routes it to the
    matching virtual primitive, which converges the outer payload. What FastMCP
    cannot see is a *plain* tool whose arguments embed versioned models — a
    nested entry carrying its own ``kind``/``version``. This middleware migrates
    each embedded entry in place before the tool's handler runs, and rewrites the
    request only when something changed.

    It is deliberately narrow: no per-kind policy resolution, no graph rebuild,
    and no concern for how the outer call's version was negotiated.
    """

    def __init__(self, registry) -> None:
        self._registry = registry

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ) -> ToolResult:
        params = context.message
        arguments = params.arguments or {}
        converged = self._registry.converge_payload(arguments)
        if converged == arguments:
            return await call_next(context)
        new_params = params.model_copy(update={"arguments": converged})
        return await call_next(context.copy(message=new_params))
