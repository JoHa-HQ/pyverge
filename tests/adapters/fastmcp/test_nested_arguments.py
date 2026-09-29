"""End-to-end: a tool whose registered model references versioned kinds.

A per-kind policy on the tool's ``meta`` drives nested convergence; a
declared-but-unregistered nested kind, and a schema that drifts from its
registered model, each fail the discovery lifecycle at startup.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
import semver
from fastmcp import Client, FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ToolDiscovery, ToolReflection
from pyverge.core import MissingReferenceError, ModelConflictError
from pyverge.migration import MigrationSettings, PydanticModelAdapter
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
                    ((AddressV3, AddressV2), migrate_address_300_200),
                    ((ContactV1, ContactV2), migrate_contact_100_200),
                ],
            ],
            id="pydantic",
        ),
    ],
    indirect=["model_adapter", "registry"],
)
async def test_per_kind_policy_drives_nested_convergence(manager) -> None:
    """A per-kind policy converges each embedded kind to its own target.

    The tool is pinned to ``latest``; the embedded ``Address`` is pinned to
    ``2.0.0`` even though ``3.0.0`` is the latest — so the nested entry
    downgrades while the outer payload converges forward.
    """
    instance = manager()
    discovery = ToolDiscovery(instance, [ToolReflection(instance.adapter)])

    @asynccontextmanager
    async def app_lifespan(server: FastMCP):
        await discovery.search(server)
        discovery.register()
        await discovery.enrich(server)
        yield {}

    server = FastMCP("TestServer", lifespan=app_lifespan)

    @server.tool(
        name="Person",
        version="2.0.0",
        meta={"policy": {"*": "latest", "Address": "2.0.0"}},
    )
    def person(
        name: str,
        address: dict,
        contacts: list[dict],
        email: str | None = None,
    ) -> dict:
        return {"name": name, "address": address, "contacts": contacts}

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

    address = result.structured_content["address"]
    assert address["version"] == "2.0.0"
    assert "region" not in address
