"""Tool discovery — index ``(kind, version) -> tool`` for a FastMCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


class ToolDiscovery:
    def __init__(self) -> None:
        self._physical: dict[tuple[str, str], Any] = {}

    async def search(self, server: FastMCP) -> dict[tuple[str, str], Any]:
        self._physical.clear()
        for tool in await server.list_tools():
            if tool.version is None:
                continue
            self._physical[(tool.name, str(tool.version))] = tool
        return self._physical
