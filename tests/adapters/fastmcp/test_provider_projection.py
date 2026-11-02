# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end: virtual versions, ranges, transforms, and provider-owned primitives."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from fastmcp import Client, FastMCP
from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.function_resource import FunctionResource
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.server.transforms import VersionFilter

from pyverge.adapters.fastmcp import (
    PromptKind,
    PyvergeProvider,
    ResourceKind,
)
from pyverge.core import MigrationContext
from pyverge.schemas import PydanticModelAdapter
from tests.examples.pydantic.semver import UserV1, UserV2, migrate_v1_to_v2

REGISTRY = [
    semver.Version,
    "test",
    [UserV1, UserV2],
    [((UserV1, UserV2), migrate_v1_to_v2)],
]


def _handler(
    name: str,
    email: str,
    role: str,
    age: int | None = None,
) -> dict[str, Any]:
    return {"name": name, "email": email, "role": role, "age": age}


def _versions(components: Any) -> set[str]:
    return {
        version
        for component in components
        for version in component.meta["fastmcp"]["versions"]
    }


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_virtual_versions_are_opt_in(manager) -> None:
    instance = manager()
    provider = PyvergeProvider(instance)
    provider.tool(_handler, name="User", version="2.0.0")

    async with Client(FastMCP("TestServer", providers=[provider])) as client:
        tools = await client.list_tools()

    assert _versions(tools) == {"2.0.0"}

    enabled = PyvergeProvider(instance, virtual_versions=True)
    enabled.tool(_handler, name="User", version="2.0.0")

    async with Client(FastMCP("TestServer", providers=[enabled])) as client:
        tools = await client.list_tools()

    assert _versions(tools) == {"1.0.0", "2.0.0"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_attached_provider_prepares_the_server(manager) -> None:
    provider = PyvergeProvider(manager(), virtual_versions=True)
    server = FastMCP("TestServer", providers=[provider])

    @server.tool(name="User", version="2.0.0", meta={"policy": "latest"})
    def handler(
        name: str, email: str, role: str, age: int | None = None
    ) -> dict[str, Any]:
        return {"name": name, "email": email, "role": role, "age": age}

    async with Client(server) as client:
        tools = await client.list_tools()

    assert _versions(tools) == {"1.0.0", "2.0.0"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_virtual_prompt_versions(manager) -> None:
    provider = PyvergeProvider(manager(), kinds=(PromptKind(),), virtual_versions=True)
    server = FastMCP("TestServer", providers=[provider])

    @server.prompt(name="User", version="2.0.0", meta={"policy": "latest"})
    def user_prompt(name: str, email: str, role: str, age: int | None = None) -> str:
        return name

    async with Client(server) as client:
        prompts = await client.list_prompts()

    assert _versions(prompts) == {"1.0.0", "2.0.0"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_virtual_resource_versions(manager) -> None:
    provider = PyvergeProvider(
        manager(),
        kinds=(ResourceKind(uri_scheme="user://"),),
        virtual_versions=True,
    )
    server = FastMCP("TestServer", providers=[provider])

    @server.resource(
        "user://{name}{?email,role,age}",
        name="User",
        version="2.0.0",
        meta={"policy": "latest"},
    )
    def user_resource(
        name: str,
        email: str = "",
        role: str = "",
        age: int | None = None,
    ) -> str:
        return name

    async with Client(server) as client:
        templates = await client.list_resource_templates()

    assert _versions(templates) == {"1.0.0", "2.0.0"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_range_policy_resolves_to_highest_match(manager) -> None:
    provider = PyvergeProvider(manager(), virtual_versions=True)
    provider.tool(
        _handler,
        name="User",
        version="2.0.0",
        meta={"policy": {"gte": "1.0.0", "lt": "3.0.0"}},
    )
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        result = await client.call_tool(
            "User",
            {"name": "A", "email": "a@b.c", "role": "user"},
            version="1.0.0",
        )

    assert result.structured_content["age"] is None


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry", [[PydanticModelAdapter, REGISTRY]], indirect=True
)
async def test_provider_transforms_run_after_sync(manager) -> None:
    provider = PyvergeProvider(
        manager(),
        virtual_versions=True,
        transforms=(VersionFilter(version_lt="2.0.0"),),
    )
    server = FastMCP("TestServer", providers=[provider])

    @server.tool(name="User", version="2.0.0", meta={"policy": "latest"})
    def handler(
        name: str, email: str, role: str, age: int | None = None
    ) -> dict[str, Any]:
        return {"name": name, "email": email, "role": role, "age": age}

    async with Client(server) as client:
        tools = await client.list_tools()

    assert _versions(tools) == {"1.0.0"}


@pytest.mark.anyio
async def test_provider_owns_prompt_resource_and_template(manager) -> None:
    provider = PyvergeProvider(manager())

    def prompt_fn(name: str) -> str:
        return name

    def static() -> str:
        return "reading"

    def templated(name: str) -> str:
        return name

    provider.add_prompt(
        FunctionPrompt.from_function(
            prompt_fn, name="Brief", version="1.0.0", meta={"policy": "latest"}
        )
    )
    provider.add_resource(
        FunctionResource.from_function(
            static,
            "brief://static",
            name="Reading",
            version="1.0.0",
            meta={"policy": "latest"},
        )
    )
    provider.add_template(
        FunctionResourceTemplate.from_function(
            templated,
            uri_template="brief://{name}",
            name="Card",
            version="1.0.0",
            meta={"policy": "latest"},
        )
    )
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        prompts = await client.list_prompts()
        resources = await client.list_resources()
        templates = await client.list_resource_templates()

    assert {prompt.name for prompt in prompts} == {"Brief"}
    assert {str(resource.uri) for resource in resources} == {"brief://static"}
    assert {template.name for template in templates} == {"Card"}


CONTEXT_AGE = 42
FACTORY_AGE = 7


def _add_age_from_context(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    return {**data, "age": (context or {}).get("age")}


CONTEXT_REGISTRY = [
    semver.Version,
    "test",
    [UserV1, UserV2],
    [((UserV1, UserV2), _add_age_from_context)],
]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, CONTEXT_REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_context_reaches_migrations(manager) -> None:
    provider = PyvergeProvider(
        manager(),
        virtual_versions=True,
        context=MigrationContext.create({"age": CONTEXT_AGE}),
    )
    provider.tool(_handler, name="User", version="2.0.0")
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        result = await client.call_tool(
            "User",
            {"name": "A", "email": "a@b.c", "role": "user"},
            version="1.0.0",
        )

    assert result.structured_content["age"] == CONTEXT_AGE


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [pytest.param(PydanticModelAdapter, CONTEXT_REGISTRY, id="pydantic")],
    indirect=True,
)
async def test_context_factory_uses_fastmcp_context(manager) -> None:
    provider = PyvergeProvider(
        manager(),
        virtual_versions=True,
        context_factory=lambda context: MigrationContext.create({"age": FACTORY_AGE}),
    )
    provider.tool(_handler, name="User", version="2.0.0")
    server = FastMCP("TestServer", providers=[provider])

    async with Client(server) as client:
        result = await client.call_tool(
            "User",
            {"name": "A", "email": "a@b.c", "role": "user"},
            version="1.0.0",
        )

    assert result.structured_content["age"] == FACTORY_AGE
