"""ToolDiscovery indexes physical versioned tools by ``(kind, version)``."""

from __future__ import annotations

import asyncio

from pyverge.adapters.fastmcp.discovery import ToolDiscovery


class _FakeTool:
    def __init__(self, name, version, parameters):
        self.name = name
        self.version = version
        self.parameters = parameters


class _FakeServer:
    def __init__(self, tools):
        self._tools = tools

    async def list_tools(self):
        return self._tools


def _search(server):
    return asyncio.run(ToolDiscovery().search(server))


class TestToolDiscovery:
    def test_indexes_versioned_only(self):
        server = _FakeServer(
            [
                _FakeTool("search_weather", "1.0.0", {"properties": {}}),
                _FakeTool("search_weather", "2.0.0", {"properties": {}}),
                _FakeTool("echo", None, {"properties": {}}),
            ]
        )
        assert set(_search(server)) == {
            ("search_weather", "1.0.0"),
            ("search_weather", "2.0.0"),
        }

    def test_skips_unversioned(self):
        server = _FakeServer([_FakeTool("echo", None, {"properties": {}})])
        assert _search(server) == {}
