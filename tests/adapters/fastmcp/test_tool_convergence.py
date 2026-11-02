# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end: tool and action payloads converge before the handler runs.

Every case drives a real FastMCP server through ``Client``. The handler stands
in for the side effect; what matters is the shape it receives.
"""

from __future__ import annotations

from typing import Any

import pytest
import semver
from fastmcp import Client, FastMCP
from fastmcp_case import Case

from pyverge.adapters.fastmcp import PyvergeProvider
from pyverge.schemas import JsonSchemaModelAdapter, PydanticModelAdapter
from tests.examples.json import USER_V1_0_0, USER_V2_0_0
from tests.examples.pydantic.semver import (
    UserV1,
    UserV2,
    migrate_v1_to_v2,
)
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    AddressV3,
    ContactV1,
    ContactV2,
    PersonV1,
    PersonV2,
    migrate_address_100_200,
    migrate_address_300_200,
    migrate_contact_100_200,
    preserve_children_person,
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
                [((USER_V1_0_0, USER_V2_0_0), lambda d, _: {**d, "age": None})],
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
            [
                semver.Version,
                "nested_test",
                [
                    PersonV1,
                    PersonV2,
                    AddressV1,
                    AddressV2,
                    AddressV3,
                    ContactV1,
                    ContactV2,
                ],
                [
                    ((PersonV1, PersonV2), preserve_children_person),
                    ((AddressV1, AddressV2), migrate_address_100_200),
                    ((AddressV2, AddressV3), lambda d, _: {**d, "region": None}),
                    ((AddressV3, AddressV2), migrate_address_300_200),
                    ((ContactV1, ContactV2), migrate_contact_100_200),
                ],
            ],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_nested_command_converges_before_the_action(manager) -> None:
    """An action command carries nested versioned commands.

    The outer command converges to ``latest``; the embedded ``Address`` command
    is pinned to ``2.0.0`` — so the nested entry downgrades while the action
    still receives a fully converged payload.
    """
    provider = PyvergeProvider(manager(), virtual_versions=True)
    server = FastMCP("TestServer", providers=[provider])

    @server.tool(
        name="Person",
        version="2.0.0",
        meta={"policy": {"*": "latest", "Address": "2.0.0"}},
    )
    def enable_profile(
        name: str,
        address: dict,
        contacts: list[dict],
        email: str | None = None,
    ) -> dict:
        return {
            "status": "enabled",
            "name": name,
            "address": address,
            "contacts": contacts,
        }

    async with Client(server) as client:
        result = await client.call_tool(
            "Person",
            {
                "name": "A",
                "address": {
                    "kind": "Address",
                    "version": "3.0.0",
                    "street": "S",
                    "city": "C",
                    "country": "X",
                    "postal_code": "1",
                    "region": "R",
                },
                "contacts": [{"kind": "Contact", "version": "1.0.0", "phone": "1"}],
            },
            version="1.0.0",
        )

    content = result.structured_content
    assert content["status"] == "enabled"
    assert content["address"]["version"] == "2.0.0"
    assert "region" not in content["address"]
