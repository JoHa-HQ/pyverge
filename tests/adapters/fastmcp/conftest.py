"""End-to-end fixtures for the FastMCP adapter suites.

Tests drive the adapter through public interfaces only: a real ``FastMCP`` server
configured with a :class:`ToolRegistry` as its lifespan and a
:class:`ConvergeMiddleware` in its middleware chain, then calls go through
``server.call_tool``.  No internal wiring is assembled by the tests.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import semver
from fastmcp import FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry
from pyverge.migration import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationSettings,
)
from pyverge.types import ManagerMigrationKey

SETTINGS = MigrationSettings(
    direction="forward",
    on_missing_path="raise",
    on_missing="reconstruct_model",
)


@pytest.fixture(params=["json", "pydantic"])
def manager(request, pydantic_model_adapter, json_model_adapter) -> Manager:
    """A fresh manager, parametrized over the JSON-Schema and pydantic adapters."""
    adapter = json_model_adapter if request.param == "json" else pydantic_model_adapter
    return Manager[semver.Version].configure(SETTINGS, adapter)()


def _model_from_schema(kind: str, version: str, props: dict, required: list[str]):
    """Build a pydantic model matching a JSON-Schema registration."""
    type_map = {"string": str, "boolean": bool, "integer": int, "number": float}
    fields: dict[str, Any] = {}
    for name in required:
        if name in ("kind", "version") or name not in props:
            continue
        fields[name] = (type_map[props[name]["type"]], ...)
    for name, doc in props.items():
        if name in fields or name in ("kind", "version"):
            continue
        fields[name] = (type_map[doc["type"]], doc.get("default"))
    fields["kind"] = (str, kind)
    fields["version"] = (str, version)
    return create_model(f"{kind}_{version}".replace(".", "_"), **fields)


def store_model(
    manager: Manager, kind: str, version: str, props: dict, required: list[str]
) -> None:
    """Register one versioned model, shaped for the manager's adapter."""
    props = dict(props)
    props.setdefault("kind", {"type": "string", "default": kind})
    props.setdefault("version", {"type": "string", "default": version})
    if isinstance(manager.engine.adapter, JsonSchemaModelAdapter):
        document = {
            "kind": kind,
            "version": version,
            "type": "object",
            "properties": props,
            "required": required,
        }
        manager.store_model(document)  # ty: ignore[invalid-argument-type]
    else:
        manager.store_model(_model_from_schema(kind, version, props, required))


def store_patch(manager: Manager, kind: str, spec: dict) -> None:
    """Register one RFC 6902 JSON Patch migration for *kind*."""
    manager.store_migration(
        ManagerMigrationKey(kind, spec["from"], spec["to"]),
        JsonPatchMigration(spec).patch,
    )


@pytest.fixture
def weather_manager(manager: Manager) -> Manager:
    """A manager owning ``search_weather`` v1 -> v2 (adds humidity)."""
    store_model(
        manager, "search_weather", "1.0.0", {"city": {"type": "string"}}, ["city"]
    )
    store_model(
        manager,
        "search_weather",
        "2.0.0",
        {"city": {"type": "string"}, "humidity": {"type": "boolean", "default": False}},
        ["city"],
    )
    store_patch(
        manager,
        "search_weather",
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/humidity", "value": False}],
        },
    )
    return manager


def running_server(manager: Manager, mcp: FastMCP, **registry_kwargs) -> FastMCP:
    """Wire *manager* into *mcp* and run the reflection lifecycle once.

    The registry is the lifespan hook; the middleware converges each call.
    """
    registry = ToolRegistry(manager, **registry_kwargs)
    mcp.middleware = [*mcp.middleware, ConvergeMiddleware(registry)]

    async def _lifecycle() -> None:
        async with registry(mcp):
            pass

    asyncio.run(_lifecycle())
    return mcp


def call_tool(mcp: FastMCP, name: str, arguments: dict):
    """Call a tool synchronously; the public call surface."""
    return asyncio.run(mcp.call_tool(name, arguments))
