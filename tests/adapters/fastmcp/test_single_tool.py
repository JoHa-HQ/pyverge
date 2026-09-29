"""End-to-end: one physical tool serves every registered version of its kind.

Each adapter carries its own tool case, because the materialized model surface
differs: the pydantic models declare ``name, email, role, age``; the JSON-schema
examples materialize to ``name, age``. The version graph comes from the shared
``registry`` fixture; calls go through the live ``client`` fixture, whose session
runs the discovery lifecycle (the server's lifespan).
"""

from __future__ import annotations

from typing import Any

import pytest
import semver
from conftest import Case
from fastmcp import FastMCP

from pyverge.adapters.fastmcp import (
    PromptReflection,
    ResourceReflection,
    ToolDiscovery,
    ToolReflection,
)
from pyverge.migration import PydanticModelAdapter
from pyverge.ports import JsonSchemaModelAdapter
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    migrate_v1_to_v2,
)


def _rich_handler(
    name: str, email: str, role: str, age: int | None = None
) -> dict[str, Any]:
    """Physical tool for the pydantic chain; signature *is* the v2 model."""
    return {"name": name, "email": email, "role": role, "age": age}


def _lean_handler(name: str, age: int | None = None) -> dict[str, Any]:
    """Physical tool for the JSON-schema chain (materializes to name, age)."""
    return {"name": name, "age": age}


RICH_CALLS = (
    Case(
        id="v1-call-converges",
        kind="User",
        version="2.0.0",
        handler=_rich_handler,
        policies={"User": "latest"},
        args={"name": "A", "email": "a@b.c", "role": "user"},
        expected={"name": "A", "email": "a@b.c", "role": "user", "age": None},
        call_version="1.0.0",
    ),
    Case(
        id="v2-call-serves",
        kind="User",
        version="2.0.0",
        handler=_rich_handler,
        policies={"User": "latest"},
        args={"name": "A", "email": "a@b.c", "role": "user"},
        expected={"name": "A", "email": "a@b.c", "role": "user", "age": None},
        call_version="2.0.0",
    ),
)

LEAN_CALLS = (
    Case(
        id="v1-call-converges",
        kind="User",
        version="2.0.0",
        handler=_lean_handler,
        policies={"User": "latest"},
        args={"name": "A"},
        expected={"name": "A", "age": None},
        call_version="1.0.0",
    ),
    Case(
        id="v2-call-serves",
        kind="User",
        version="2.0.0",
        handler=_lean_handler,
        policies={"User": "latest"},
        args={"name": "A"},
        expected={"name": "A", "age": None},
        call_version="2.0.0",
    ),
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry, case",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "user_test",
                [UserV1, UserV2],
                [((UserV1, UserV2), migrate_v1_to_v2)],
            ],
            rich_call,
            id=f"pydantic-{rich_call.id}",
        )
        for rich_call in RICH_CALLS
    ]
    + [
        pytest.param(
            JsonSchemaModelAdapter,
            [
                semver.Version,
                "user_test",
                [USER_V1_0_0, USER_V2_0_0],
                [((USER_V1_0_0, USER_V2_0_0), lambda d: {**d, "age": None})],
            ],
            lean_call,
            id=f"json-{lean_call.id}",
        )
        for lean_call in LEAN_CALLS
    ],
    indirect=["model_adapter", "registry", "case"],
)
async def test_call_at_any_version_reaches_the_handler(client, case: Case) -> None:
    result = await client.call_tool(case.kind, case.args, version=case.call_version)
    assert result.structured_content == case.expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry, case",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "user_test", [], []],
            Case(
                id="unrelated",
                kind="unrelated",
                handler=lambda a: {"a": a},
                policies={},
                args={"a": "x"},
                expected={"a": "x"},
            ),
            id="pydantic-unrelated",
        ),
    ],
    indirect=["model_adapter", "registry", "case"],
)
async def test_unrelated_tool_is_left_untouched(client, case: Case) -> None:
    result = await client.call_tool(case.kind, case.args)
    assert result.structured_content == case.expected


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "user_test", [UserV1, UserV2], []],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_owned_kind_without_policy_fails_fast(manager: type) -> None:
    """A versioned primitive of an owned kind but with no policy fails the lifecycle.

    There is no silent default: every exposed kind needs an explicit policy.
    """
    instance = manager()
    discovery = ToolDiscovery(instance, [ToolReflection(instance.adapter)])
    server = FastMCP("TestServer")
    server.tool(_rich_handler, name="User", version="2.0.0")

    with pytest.raises(ValueError, match="has no policy"):
        await discovery.search(server)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "user_test", [UserV1, UserV2], []],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_policy_declared_in_meta(manager: type) -> None:
    """A primitive declares its policy via ``meta['policy']`` — no map needed."""
    instance = manager()
    discovery = ToolDiscovery(instance, [ToolReflection(instance.adapter)])
    server = FastMCP("TestServer")
    server.tool(_rich_handler, name="User", version="2.0.0", meta={"policy": "latest"})

    await discovery.search(server)
    discovery.register()
    await discovery.enrich(server)

    names = {t.name for t in await server.list_tools()}
    assert names == {"User"}


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "user_test", [UserV1, UserV2], []],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_conflicting_meta_policies_fail(manager: type) -> None:
    """Versions of one kind must agree on their declared policy."""
    instance = manager()
    discovery = ToolDiscovery(instance, [ToolReflection(instance.adapter)])
    server = FastMCP("TestServer")
    server.tool(_rich_handler, name="User", version="1.0.0", meta={"policy": "latest"})
    server.tool(
        _rich_handler, name="User", version="2.0.0", meta={"policy": "earliest"}
    )

    with pytest.raises(ValueError, match="conflicting policies"):
        await discovery.search(server)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry",
    [
        pytest.param(
            PydanticModelAdapter,
            [semver.Version, "user_test", [UserV1, UserV2], []],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_meta_policy_on_prompt_and_resource(manager: type) -> None:
    """Prompt and resource primitives declare their policy via meta too."""
    instance = manager()
    server = FastMCP("TestServer")

    @server.prompt(name="User", version="2.0.0", meta={"policy": "latest"})
    def user_prompt(name: str, email: str, role: str, age: int | None = None) -> str:
        return name

    @server.resource(
        "userres://{name}", name="User", version="2.0.0", meta={"policy": "latest"}
    )
    def user_resource(name: str) -> str:
        return name

    # Each provider alone passes search because its meta declares a policy.
    prompts = ToolDiscovery(instance, [PromptReflection(instance.adapter)])
    resources = ToolDiscovery(instance, [ResourceReflection(instance.adapter)])
    await prompts.search(server)
    await resources.search(server)
