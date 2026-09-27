"""Shared fixtures for the FastMCP adapter suites.

Common plumbing is factored into fixtures so each usage case stays a thin,
self-contained suite:

* :func:`manager` — a fresh manager instance (no registrations),
  parametrized over the JSON-Schema and pydantic model adapters,
* :func:`store_schema` / :func:`store_patch` — registration helpers that
  build the right model shape for the manager's bound adapter,
* :func:`weather_chain` — a manager owning ``search_weather`` v1→v2,
* :func:`configured_server` — a fully configured FastMCP server: registers
  the models against the managers, reflects/registers/enriches a server and
  returns ``(mcp, registry)``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import semver
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ToolRegistry
from pyverge.migration import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationSettings,
)
from pyverge.types import ManagerMigrationKey


@pytest.fixture(params=["json", "pydantic"])
def manager(request, pydantic_model_adapter, json_model_adapter) -> Manager:
    """A fresh manager instance, parametrized over the model adapter.

    The FastMCP suites run against both the JSON-Schema adapter (raw schemas
    registered as dicts) and the pydantic adapter (models built with
    ``create_model``), so the routing fixture inherits the selected adapter.
    """
    adapter = json_model_adapter if request.param == "json" else pydantic_model_adapter
    UserManager = Manager[semver.Version].configure(
        MigrationSettings(
            direction="forward",
            on_missing_path="raise",
            on_missing="reconstruct_model",
        ),
        adapter,
    )
    return UserManager()


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


def _store_model(
    manager: Manager,
    kind: str,
    version: str,
    props: dict,
    required: list[str],
) -> None:
    """Register one versioned model for *kind* into *manager*.

    The input shape depends on the adapter the manager is bound to: a raw
    JSON-Schema dict for the JSON adapter, a pydantic model otherwise.
    """
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


@pytest.fixture
def store_schema():
    """Register one versioned model for *kind* into *manager*."""

    def _store(
        manager: Manager,
        kind: str,
        version: str,
        props: dict,
        required: list[str],
    ) -> None:
        _store_model(manager, kind, version, props, required)

    return _store


@pytest.fixture
def store_patch():
    """Register one RFC 6902 JSON Patch migration for *kind*."""

    def _store(manager: Manager, kind: str, spec: dict) -> None:
        manager.store_migration(
            ManagerMigrationKey(kind, spec["from"], spec["to"]),
            JsonPatchMigration(spec).patch,
        )

    return _store


@pytest.fixture
def weather_chain(manager: Manager, store_schema, store_patch) -> Manager:
    """A manager owning a ``search_weather`` chain: v1 → v2 (adds humidity)."""
    store_schema(
        manager, "search_weather", "1.0.0", {"city": {"type": "string"}}, ["city"]
    )
    store_schema(
        manager,
        "search_weather",
        "2.0.0",
        {
            "city": {"type": "string"},
            "humidity": {"type": "boolean", "default": False},
        },
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


@pytest.fixture
def configured_server():
    """Return a fully configured FastMCP server: ``(mcp, registry)``.

    Runs the registry's real lifespan (search → register → enrich) against the
    given server instance, then hands the pair back for assertions and calling.
    """

    async def _lifecycle(registry: ToolRegistry, mcp) -> None:
        async with registry(mcp):
            pass

    def _configure(
        managers: Manager | list[Manager],
        mcp,
        **registry_kwargs,
    ):
        registry = ToolRegistry(managers, **registry_kwargs)
        asyncio.run(_lifecycle(registry, mcp))
        return mcp, registry

    return _configure
