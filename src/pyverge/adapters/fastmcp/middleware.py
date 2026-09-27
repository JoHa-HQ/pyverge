"""ConvergeMiddleware — converge tool-call arguments per call.

The middleware reads the path precomputed by :class:`ToolRegistry` per call:
discover ``(kind, version)`` → look up the precomputed path → converge. Each
call resolves the precomputed delegate straight off the registry, so no graph
rebuild and no per-call policy resolution. A versioned call is fully served by
the converging delegate; an unversioned call converges only its embedded
versioned entries and forwards to the tool's own handler.

An optional ``span_factory`` wraps each call in a parent span. The per-migration
hooks attached by :class:`ToolRegistry` then nest their step spans under it, so a
trace shows the tool call with one child span per migration step. The factory is
an injected callable, so this module stays free of any tracing library.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware
from fastmcp.tools.base import ToolResult
from mcp.types import CallToolRequestParams

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext

#: Opens a parent span for a call; ``None`` means the default no-op.
SpanFactory = Callable[[str], AbstractContextManager[Any]]


@contextmanager
def _no_span(name: str) -> Iterator[None]:
    yield


class ConvergeMiddleware(Middleware):
    """Converge tool-call arguments to the precomputed policy target."""

    def __init__(self, registry, *, span_factory: SpanFactory | None = None) -> None:
        self._registry = registry
        self._span_factory = span_factory or _no_span

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ) -> ToolResult:
        params = context.message
        kind = params.name
        arguments = params.arguments or {}
        # Discover the version the call was made against: the native FastMCP
        # negotiation (`meta.fastmcp.version`) first, then the pyverge
        # bookkeeping field in the arguments.  No marker → the tool is
        # unversioned: converge only its embedded versioned entries and pass
        # through to the tool's own handler.
        version = self._requested_version(params, arguments)
        with self._span_factory(self._span_name(kind, version)):
            if version is None:
                return await self._converge_unversioned(context, call_next)
            delegate = self._registry.delegate(kind, str(version))
            if delegate is None:
                return await call_next(context)
            return ToolResult(structured_content=delegate(**arguments))

    @staticmethod
    def _span_name(kind: str, version: str | None) -> str:
        return f"{kind}@{version}" if version else kind

    @staticmethod
    def _requested_version(
        params: CallToolRequestParams, arguments: dict
    ) -> str | None:
        meta = params.meta or {}
        fastmcp_meta = meta.get("fastmcp") if isinstance(meta, dict) else None
        version = (
            fastmcp_meta.get("version") if isinstance(fastmcp_meta, dict) else None
        )
        return version or arguments.get("version")

    async def _converge_unversioned(self, context, call_next) -> ToolResult:
        """Converge a call with no version marker to the latest models.

        A plain (unversioned) tool may still embed versioned models in its
        arguments.  Converging without a version keeps the passthrough fast and
        preserves the tool's own handler: only embedded versioned entries are
        migrated.
        """
        params = context.message
        arguments = params.arguments or {}
        converged = self._registry.converge_payload(arguments)
        if converged is None:
            return await call_next(context)
        new_params = params.model_copy(update={"arguments": converged})
        return await call_next(context.copy(message=new_params))
