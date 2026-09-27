"""Server wiring and convergence tests.

Runs the real FastMCP reflection lifecycle through the DI container and asserts
that a call at any registered version converges to the anchor handler, using the
precomputed convergence path.
"""

from __future__ import annotations

from conftest import FAKE_READING
from fastmcp_demo.domain import V1, V2, V3


class TestServerWiring:
    async def test_path_precomputed_for_oldest_version(self, prepared) -> None:
        assert prepared.registry.path(prepared.kind, V1) == V3

    async def test_delegate_exists_for_every_version(self, prepared) -> None:
        for version in (V1, V2, V3):
            assert prepared.registry.delegate(prepared.kind, version) is not None


class TestConvergence:
    async def test_calls_converge_to_anchor_shape(self, prepared) -> None:
        results = dict(prepared.demo_calls())
        expected = {
            "city": "Berlin",
            "units": "celsius",
            "temperature": FAKE_READING.temperature,
            "humidity": FAKE_READING.humidity,
            "wind": FAKE_READING.wind,
        }
        # Every registered version converges to the anchor handler's shape.
        for version in (V1, V2, V3):
            assert results[version] == expected

    async def test_unversioned_payload_is_not_converged(self, prepared) -> None:
        assert prepared.registry.converge_payload({"foo": "bar"}) is None


class TestToolInjection:
    async def test_injected_service_is_not_in_the_schema(self, prepared) -> None:
        """The physical tool's reflected schema matches the anchor contract.

        The ``weather`` service is injected via the container; it must be hidden
        from the exposed signature, or the adapter's reconcile would reject it.
        """
        tools = await prepared.server.list_tools()
        physical = next(t for t in tools if str(t.version) == V3)
        assert set(physical.parameters["properties"]) == {
            "kind",
            "version",
            "city",
            "units",
            "temperature",
            "humidity",
            "wind",
        }

    async def test_injected_service_serves_the_call(self, prepared) -> None:
        delegate = prepared.registry.delegate(prepared.kind, V3)
        assert delegate is not None
        assert delegate(city="Berlin")["temperature"] == FAKE_READING.temperature
