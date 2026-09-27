from __future__ import annotations

import asyncio

import pytest

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


class TestToolDiscovery:
    def test_indexes_versioned_only(
        self,
    ):
        server = _FakeServer(
            [
                _FakeTool(
                    "search_weather",
                    "1.0.0",
                    {"properties": {"city": {"type": "string"}}},
                ),
                _FakeTool(
                    "search_weather",
                    "2.0.0",
                    {
                        "properties": {
                            "city": {"type": "string"},
                            "humidity": {"type": "boolean"},
                        }
                    },
                ),
                _FakeTool("echo", None, {"properties": {"msg": {"type": "string"}}}),
            ]
        )
        discovery = ToolDiscovery()

        asyncio.run(discovery.discover(server))  # ty: ignore[invalid-argument-type]
        assert set(discovery.tools()) == {"search_weather"}
        assert discovery.versions("search_weather") == ["1.0.0", "2.0.0"]
        assert discovery.versions("echo") == []

    def test_schema_latest_when_version_omitted(self):
        server = _FakeServer(
            [
                _FakeTool("t", "1.0.0", {"properties": {"a": {"type": "string"}}}),
                _FakeTool("t", "2.0.0", {"properties": {"b": {"type": "string"}}}),
            ]
        )
        discovery = ToolDiscovery()

        asyncio.run(discovery.discover(server))  # ty: ignore[invalid-argument-type]
        assert discovery.schema("t")["properties"] == {"b": {"type": "string"}}

    def test_schema_specific_version(self):
        server = _FakeServer(
            [_FakeTool("t", "1.0.0", {"properties": {"a": {"type": "string"}}})]
        )
        discovery = ToolDiscovery()

        asyncio.run(discovery.discover(server))  # ty: ignore[invalid-argument-type]
        assert discovery.schema("t", "1.0.0")["properties"] == {"a": {"type": "string"}}

    def test_unknown_tool_raises(self):
        discovery = ToolDiscovery()
        with pytest.raises(KeyError, match="unknown tool"):
            discovery.schema("nope")

    def test_unknown_version_raises(self):
        server = _FakeServer([_FakeTool("t", "1.0.0", {"properties": {}})])
        discovery = ToolDiscovery()

        asyncio.run(discovery.discover(server))  # ty: ignore[invalid-argument-type]
        with pytest.raises(KeyError, match="unknown version"):
            discovery.schema("t", "9.9.9")

    def test_versions_unknown_kind_empty(self):
        discovery = ToolDiscovery()
        assert discovery.versions("nope") == []
