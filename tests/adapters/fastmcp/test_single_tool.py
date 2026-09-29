"""End-to-end: one physical tool serves every registered version of its kind.

Each adapter carries its own tool case, because the materialized model surface
differs: the pydantic models declare ``name, email, role, age``; the JSON-schema
examples materialize to ``name, age``.  The version graph comes from the shared
``registry`` fixture; calls go through the public ``server.call_tool`` surface.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pytest
import semver
from conftest import call_tool, serve
from fastmcp import FastMCP

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


@dataclass(frozen=True)
class ToolCase:
    """A tool declaration plus the convergence a call must perform."""

    id: str
    kind: str
    version: str
    handler: Callable[..., Any]
    args: dict[str, Any]
    expected: dict[str, Any]


RICH_CALLS = (
    ToolCase(
        id="v1-call-converges",
        kind="User",
        version="2.0.0",
        handler=_rich_handler,
        args={"name": "A", "email": "a@b.c", "role": "user", "version": "1.0.0"},
        expected={"name": "A", "email": "a@b.c", "role": "user", "age": None},
    ),
    ToolCase(
        id="v2-call-serves",
        kind="User",
        version="2.0.0",
        handler=_rich_handler,
        args={"name": "A", "email": "a@b.c", "role": "user", "version": "2.0.0"},
        expected={"name": "A", "email": "a@b.c", "role": "user", "age": None},
    ),
)

LEAN_CALLS = (
    ToolCase(
        id="v1-call-converges",
        kind="User",
        version="2.0.0",
        handler=_lean_handler,
        args={"name": "A", "version": "1.0.0"},
        expected={"name": "A", "age": None},
    ),
    ToolCase(
        id="v2-call-serves",
        kind="User",
        version="2.0.0",
        handler=_lean_handler,
        args={"name": "A", "version": "2.0.0"},
        expected={"name": "A", "age": None},
    ),
)


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
    indirect=["model_adapter", "registry"],
)
def test_call_at_any_version_reaches_the_handler(
    manager: type, registry, case: ToolCase
) -> None:
    mcp = FastMCP("S")
    mcp.tool(case.handler, name=case.kind, version=case.version)

    serve(manager, mcp, policies={case.kind: "latest"})
    result = call_tool(mcp, case.kind, case.args)

    assert result.structured_content == case.expected


def test_unrelated_tool_is_left_untouched(manager: type, registry) -> None:
    mcp = FastMCP("S")

    @mcp.tool
    def unrelated(a: str) -> dict[str, Any]:
        return {"a": a}

    serve(manager, mcp, policies={"User": "latest"})
    result = call_tool(mcp, "unrelated", {"a": "x"})

    assert result.structured_content == {"a": "x"}
