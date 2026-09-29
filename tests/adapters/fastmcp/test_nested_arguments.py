"""End-to-end: a tool whose arguments embed versioned models.

A plain tool (stable signature) carries an argument that is a versioned model.
The middleware converges every embedded entry to its chain's latest version
before the handler runs. A declared-but-unregistered nested kind, and a schema
that drifts from its registered model, each fail the discovery lifecycle at
startup.
"""

from __future__ import annotations

import pytest
import semver
from conftest import Case
from fastmcp import FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ToolDiscovery, ToolReflection
from pyverge.core import MissingReferenceError, ModelConflictError
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    migrate_address_100_200,
)

EMBEDDED = Case(
    id="embedded",
    kind="search",
    handler=lambda location: {"location": location},
    policies={},
    args={
        "location": {
            "kind": "Address",
            "version": "1.0.0",
            "street": "S",
            "city": "C",
        }
    },
    expected={
        "location": {
            "kind": "Address",
            "version": "2.0.0",
            "street": "S",
            "city": "C",
            "country": None,
            "postal_code": None,
        }
    },
)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "model_adapter, registry, case",
    [
        pytest.param(
            PydanticModelAdapter,
            [
                semver.Version,
                "nested_test",
                [AddressV1, AddressV2],
                [((AddressV1, AddressV2), migrate_address_100_200)],
            ],
            EMBEDDED,
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry", "case"],
)
async def test_embedded_model_converges_before_the_handler(client, case: Case) -> None:
    result = await client.call_tool(case.kind, case.args)
    assert result.structured_content == case.expected


async def _run_lifecycle(discovery: ToolDiscovery, server: FastMCP) -> None:
    await discovery.search(server)
    discovery.register()
    await discovery.enrich(server)


class TestUnregisteredReference:
    @pytest.mark.anyio
    async def test_unregistered_nested_kind_fails_at_startup(
        self, pydantic_model_adapter
    ) -> None:
        """A tool whose registered model references an unregistered kind fails.

        The reference walk sees every declared version; an absent one is a
        latent bug (the walker skips unregistered kinds), so the adapter fails
        the discovery lifecycle instead of silently serving stale children.
        """
        manager = Manager[semver.Version].configure(
            MigrationSettings(on_missing="reconstruct_model"), pydantic_model_adapter
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

        mcp = FastMCP("S")

        @mcp.tool(name="search_weather", version="2.0.0")
        def search_weather(location: dict) -> dict:
            return {"location": location}

        discovery = ToolDiscovery(
            manager,
            [ToolReflection(manager.adapter)],
            policies={"search_weather": "latest"},
        )

        with pytest.raises(MissingReferenceError, match="not registered"):
            await _run_lifecycle(discovery, mcp)


class TestSchemaConflict:
    @pytest.mark.anyio
    async def test_drifting_schema_names_the_primitive(
        self, pydantic_model_adapter
    ) -> None:
        """A reflected schema that drifts from its registered model fails.

        The engine raises the conflict; discovery re-raises it naming the host
        primitive so the operator can see which entity drifted.
        """
        manager = Manager[semver.Version].configure(
            MigrationSettings(), pydantic_model_adapter
        )()
        registered = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            city=(str, ...),
        )
        manager.store_model(registered)

        mcp = FastMCP("S")

        @mcp.tool(name="search_weather", version="2.0.0")
        def search_weather(city: str, units: str = "celsius") -> dict:
            return {"city": city, "units": units}

        discovery = ToolDiscovery(
            manager,
            [ToolReflection(manager.adapter)],
            policies={"search_weather": "latest"},
        )

        with pytest.raises(ModelConflictError, match=r"primitive 'search_weather'@"):
            await _run_lifecycle(discovery, mcp)
