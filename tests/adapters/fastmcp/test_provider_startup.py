# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end: the provider lifespan gates startup on graph integrity."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from fastmcp import Client, FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import (
    PyvergeExtension,
    PyvergeProvider,
)
from pyverge.schemas import PydanticModelAdapter
from pyverge.settings import MigrationSettings, manager_kwargs
from tests.examples.pydantic.semver_nested import PersonV1


def _handler(name: str, age: int | None = None) -> dict[str, Any]:
    return {"name": name, "age": age}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "user_test", [], []]]],
    indirect=True,
)
async def test_owned_kind_without_policy_fails_startup(manager) -> None:
    provider = PyvergeProvider(manager(), virtual_versions=True)
    server = FastMCP("TestServer", providers=[provider])
    server.tool(_handler, name="User", version="2.0.0")

    with pytest.raises(RuntimeError, match="has no policy"):
        async with Client(server):
            pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "user_test", [], []]]],
    indirect=True,
)
async def test_conflicting_meta_policies_fail_startup(manager) -> None:
    provider = PyvergeProvider(manager(), virtual_versions=True)
    server = FastMCP("TestServer", providers=[provider])
    server.tool(_handler, name="User", version="1.0.0", meta={"policy": "latest"})
    server.tool(_handler, name="User", version="2.0.0", meta={"policy": "earliest"})

    with pytest.raises(RuntimeError, match="conflicting policies"):
        async with Client(server):
            pass


@pytest.mark.anyio
async def test_unregistered_nested_kind_fails_startup(pydantic_model_adapter) -> None:
    manager = Manager[semver.Version].configure(
        pydantic_model_adapter,
        **manager_kwargs(MigrationSettings(on_missing="reconstruct_model")),
    )()
    location = create_model(
        "Location", kind=(str, "location"), version=(str, "1.0.0"), city=(str, ...)
    )
    search_weather = create_model(
        "SearchWeather",
        kind=(str, "search_weather"),
        version=(str, "2.0.0"),
        location=(location, ...),
    )
    manager.store_model(search_weather)  # 'location' intentionally absent

    provider = PyvergeProvider(
        manager,
        policies={"search_weather": "latest"},
        virtual_versions=True,
    )
    server = FastMCP("S", providers=[provider])

    @server.tool(name="search_weather", version="2.0.0")
    def search_weather(location: dict) -> dict:
        return {"location": location}

    with pytest.raises(RuntimeError, match=r"reference\.missing\.local"):
        async with Client(server):
            pass


@pytest.mark.anyio
async def test_drifting_schema_names_the_primitive(pydantic_model_adapter) -> None:
    manager = Manager[semver.Version].configure(
        pydantic_model_adapter,
        **manager_kwargs(MigrationSettings()),
    )()
    registered = create_model(
        "SearchWeather",
        kind=(str, "search_weather"),
        version=(str, "2.0.0"),
        city=(str, ...),
    )
    manager.store_model(registered)

    provider = PyvergeProvider(
        manager,
        policies={"search_weather": "latest"},
        virtual_versions=True,
    )
    server = FastMCP("S", providers=[provider])

    @server.tool(name="search_weather", version="2.0.0")
    def search_weather(city: str, units: str = "celsius") -> dict:
        return {"city": city, "units": units}

    with pytest.raises(
        RuntimeError,
        match=r"search_weather@2\.0\.0 is already registered",
    ):
        async with Client(server):
            pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [PersonV1], []]]],
    indirect=True,
)
async def test_provider_lifespan_blocks_server_startup(manager) -> None:
    server = FastMCP("TestServer", providers=[PyvergeProvider(manager())])

    with pytest.raises(RuntimeError, match="Registry health validation failed"):
        async with Client(server):
            pass


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [[PydanticModelAdapter, [semver.Version, "test", [PersonV1], []]]],
    indirect=True,
)
async def test_provider_lifespan_accepts_never_fail_level(manager) -> None:
    provider = PyvergeProvider(manager(), health_fail_level="never")
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        assert await client.list_tools() == []


@pytest.mark.anyio
async def test_extension_is_advertised(manager) -> None:
    instance = manager()
    extension = PyvergeExtension(instance)
    provider = PyvergeProvider(instance, extension=extension)
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        advertised = client.server_capabilities.extensions

    assert advertised["com.joha/pyverge"] == extension.settings()
