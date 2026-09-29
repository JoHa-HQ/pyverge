"""End-to-end helpers for the FastMCP adapter suites.

Registration and model shapes come from the shared fixtures in ``tests/conftest.py``
(``model_adapter`` / ``registry`` / ``manager``, parametrized indirectly as in
``test_manager.py``).  These helpers only wire a manager into a real FastMCP
server and drive calls through the public ``server.call_tool`` surface — no
internal wiring is assembled by the tests.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry


def serve(manager_cls: type, mcp: FastMCP, **registry_kwargs: Any) -> ToolRegistry:
    """Wire *manager_cls* into *mcp* and run the reflection lifecycle once.

    The registry is the lifespan hook; the middleware converges each call.
    """
    registry = ToolRegistry(manager_cls(), **registry_kwargs)
    mcp.middleware = [*mcp.middleware, ConvergeMiddleware(registry)]

    async def _lifecycle() -> None:
        async with registry(mcp):
            pass

    asyncio.run(_lifecycle())
    return registry


def call_tool(mcp: FastMCP, name: str, arguments: dict) -> Any:
    """Call a tool synchronously; the public call surface."""
    return asyncio.run(mcp.call_tool(name, arguments))
