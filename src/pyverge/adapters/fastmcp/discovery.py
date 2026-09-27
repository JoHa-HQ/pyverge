"""Tool discovery — index ``(kind, version) -> schema`` for a FastMCP server."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastmcp import FastMCP


class ToolDiscovery:
    """Inspect a FastMCP server at startup and index its versioned tools.

    Attaches to the server's ``lifespan``.  On startup it calls ``list_tools``
    on the server object and builds a discovery index: for every **versioned**
    tool it records the kind (tool name), version, and the JSON Schema of its
    ``inputSchema`` (``parameters``).  Unversioned tools are skipped — they are
    not part of the versioned surface.
    """

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, dict]] = {}
        self._versions: dict[str, list[str]] = {}
        self._physical: dict[tuple[str, str], Any] = {}

    async def discover(self, server: FastMCP) -> None:
        """Inspect the server and index every versioned tool's schema."""
        for tool in await server.list_tools():
            if tool.version is None:
                continue
            self._tools.setdefault(tool.name, {})[str(tool.version)] = dict(
                tool.parameters
            )
            self._versions.setdefault(tool.name, []).append(str(tool.version))

    async def search(self, server: FastMCP) -> dict[tuple[str, str], Any]:
        """Return the physical versioned tools as a ``(kind, version)`` index."""
        self._physical.clear()
        for tool in await server.list_tools():
            if tool.version is None:
                continue
            self._physical[(tool.name, str(tool.version))] = tool
        return self._physical

    def physical(self) -> dict[tuple[str, str], Any]:
        """Return the physical ``(kind, version) -> tool`` index."""
        return self._physical

    def schema(self, kind: str, version: str | None = None) -> dict:
        """Return the JSON Schema for a tool at a version (default: latest)."""
        versions = self._tools.get(kind)
        if not versions:
            raise KeyError(f"unknown tool: {kind!r}")
        if version is None:
            version = self._versions[kind][-1]
        if version not in versions:
            raise KeyError(f"unknown version {version!r} for tool {kind!r}")
        return versions[version]

    def versions(self, kind: str) -> list[str]:
        """Return every registered schema version for a tool."""
        return list(self._versions.get(kind, []))

    def tools(self) -> list[str]:
        """Return every discovered tool name."""
        return list(self._tools.keys())
