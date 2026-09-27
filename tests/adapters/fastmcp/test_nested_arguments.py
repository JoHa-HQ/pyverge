"""Suite: tools whose arguments embed versioned models.

The tool itself is plain (stable schema); some arguments carry an embedded
model that is versioned.  The adapter converges every embedded versioned
entry to its chain's latest version before passing the payload on — without
touching the tool's own handler.

Parametrized over the two shapes:
* one versioned model + a primitive argument,
* two versioned models.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest
import semver
from fastmcp import FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.migration import MigrationSettings


@dataclass(frozen=True)
class Chain:
    """Declarative v1→v2 chain for an embedded model kind."""

    kind: str
    field: str
    default: str


@dataclass(frozen=True)
class Case:
    """A tool signature + the convergence it must perform."""

    id: str
    tool: str
    chains: tuple[Chain, ...]
    args: dict
    expected: dict


CASES = (
    Case(
        id="model-plus-primitive",
        tool="search_weather",
        chains=(Chain("location", "country", "DE"),),
        args={
            "location": {"kind": "location", "version": "1.0.0", "city": "Berlin"},
            "units": "metric",
        },
        expected={
            "location": {
                "kind": "location",
                "version": "2.0.0",
                "city": "Berlin",
                "country": "DE",
            },
            "units": "metric",
        },
    ),
    Case(
        id="two-models",
        tool="plan_route",
        chains=(
            Chain("origin", "zone", "A"),
            Chain("destination", "zone", "B"),
        ),
        args={
            "origin": {"kind": "origin", "version": "1.0.0", "city": "Berlin"},
            "destination": {
                "kind": "destination",
                "version": "1.0.0",
                "city": "Paris",
            },
        },
        expected={
            "origin": {
                "kind": "origin",
                "version": "2.0.0",
                "city": "Berlin",
                "zone": "A",
            },
            "destination": {
                "kind": "destination",
                "version": "2.0.0",
                "city": "Paris",
                "zone": "B",
            },
        },
    ),
)


@pytest.fixture
def chain_manager(manager: Manager, store_schema, store_patch, case: Case) -> Manager:
    for chain in case.chains:
        store_schema(
            manager, chain.kind, "1.0.0", {"city": {"type": "string"}}, ["city"]
        )
        store_schema(
            manager,
            chain.kind,
            "2.0.0",
            {
                "city": {"type": "string"},
                chain.field: {"type": "string", "default": chain.default},
            },
            ["city"],
        )
        store_patch(
            manager,
            chain.kind,
            {
                "from": "1.0.0",
                "to": "2.0.0",
                "ops": [
                    {"op": "add", "path": f"/{chain.field}", "value": chain.default}
                ],
            },
        )
    return manager


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
class TestToolArguments:
    def test_embedded_models_converge(
        self,
        chain_manager: Manager,
        configured_server,
        case: Case,
    ):
        calls: list[tuple] = []

        mcp = FastMCP("S")

        if case.tool == "search_weather":

            @mcp.tool
            def search_weather(location: dict, units: str = "celsius") -> dict:
                calls.append((location, units))
                return {"location": location, "units": units}

        else:

            @mcp.tool
            def plan_route(origin: dict, destination: dict) -> dict:
                calls.append((origin, destination))
                return {"origin": origin, "destination": destination}

        _, registry = configured_server(chain_manager, mcp)

        converged = registry.converge_payload(case.args)
        assert converged is not None
        assert converged == case.expected
        assert calls == []


class TestStrictNestedRegistration:
    def test_unregistered_nested_kind_raises(
        self,
        pydantic_model_adapter,
        configured_server,
    ):
        """A tool that *uses* an unregistered nested model fails at startup.

        No implicit registration: the adapter never writes a model into the
        engine.  A versioned tool whose registered model embeds a nested kind
        with no owning manager is a misconfiguration.
        """
        UserManager = Manager[semver.Version].configure(
            MigrationSettings(
                direction="forward",
                on_missing_path="raise",
                on_missing="reconstruct_model",
            ),
            pydantic_model_adapter,
        )
        manager = UserManager()

        location = create_model(
            "Location",
            kind=(str, "location"),
            version=(str, "1.0.0"),
            city=(str, ...),
        )
        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            location=(location, ...),
        )
        manager.store_model(search_weather)

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(location: dict) -> dict:
            return {"location": location}

        with pytest.raises(ValueError, match="not registered in any manager"):
            configured_server(
                manager,
                mcp,
                policies={"search_weather": "latest"},
            )

    def test_registered_nested_kind_serves(
        self,
        pydantic_model_adapter,
        configured_server,
    ):
        """A tool embedding a registered nested kind enriches without error."""
        UserManager = Manager[semver.Version].configure(
            MigrationSettings(
                direction="forward",
                on_missing_path="raise",
                on_missing="reconstruct_model",
            ),
            pydantic_model_adapter,
        )
        manager = UserManager()

        location = create_model(
            "Location",
            kind=(str, "location"),
            version=(str, "1.0.0"),
            city=(str, ...),
        )
        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            location=(location, ...),
        )
        manager.store_model(search_weather)
        manager.store_model(location)

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(location: dict) -> dict:
            return {"location": location}

        _, registry = configured_server(
            manager,
            mcp,
            policies={"search_weather": "latest"},
        )
        assert registry.delegate("search_weather", "2.0.0") is not None


class TestReconcileSignature:
    def test_signature_nested_kind_unregistered_raises(
        self,
        json_model_adapter,
        configured_server,
    ):
        """Reconcile fails when the *signature* embeds an unregistered nested kind.

        A tool whose parameter is typed by a versioned model reflects that
        model into its signature tree.  The lowest sub-trees must already be
        registered — there is no implicit registration at reconcile time.
        """
        UserManager = Manager[semver.Version].configure(
            MigrationSettings(
                direction="forward",
                on_missing_path="raise",
                on_missing="reconstruct_model",
            ),
            json_model_adapter,
        )
        manager = UserManager()

        location = create_model(
            "Location",
            kind=(str, "location"),
            version=(str, "1.0.0"),
            city=(str, ...),
        )
        globals()["_ReconcileLocation"] = location
        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            location=(dict, ...),
        )
        manager.store_model(search_weather)

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(location: _ReconcileLocation) -> dict:  # noqa: F821  # ty: ignore[unresolved-reference]
            return {"location": location.model_dump()}

        with pytest.raises(ValueError, match="signature uses nested model"):
            configured_server(
                manager,
                mcp,
                policies={"search_weather": "latest"},
            )

    def test_signature_drift_raises(
        self,
        json_model_adapter,
        configured_server,
    ):
        """Reconcile fails when the signature no longer matches the registered model."""
        UserManager = Manager[semver.Version].configure(
            MigrationSettings(
                direction="forward",
                on_missing_path="raise",
                on_missing="reconstruct_model",
            ),
            json_model_adapter,
        )
        manager = UserManager()

        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            city=(str, ...),
        )
        manager.store_model(search_weather)

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str, country: str = "DE") -> dict:
            return {"city": city, "country": country}

        with pytest.raises(ValueError, match="signature reflects fields"):
            configured_server(
                manager,
                mcp,
                policies={"search_weather": "latest"},
            )

    def test_matching_signature_serves(
        self,
        json_model_adapter,
        configured_server,
    ):
        """A signature agreeing with its registered contract reconciles cleanly."""
        UserManager = Manager[semver.Version].configure(
            MigrationSettings(
                direction="forward",
                on_missing_path="raise",
                on_missing="reconstruct_model",
            ),
            json_model_adapter,
        )
        manager = UserManager()

        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            city=(str, ...),
        )
        manager.store_model(search_weather)

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str) -> dict:
            return {"city": city}

        _, registry = configured_server(
            manager,
            mcp,
            policies={"search_weather": "latest"},
        )
        assert registry.delegate("search_weather", "2.0.0") is not None
