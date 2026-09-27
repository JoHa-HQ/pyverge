"""Server wiring and convergence tests.

Runs the real FastMCP reflection lifecycle against a fresh server and asserts
that a call at any registered version converges to the anchor handler, using the
precomputed convergence path.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.application import DemoService
from fastmcp_demo.settings import DemoSettings


@pytest.fixture
async def service(settings: DemoSettings) -> DemoService:
    svc = DemoService(settings, tracer=None)
    await svc.prepare()
    return svc


class TestServerWiring:
    async def test_path_precomputed_for_oldest_version(self, service) -> None:
        kind = service.kind
        assert service.registry.path(kind, "1.0.0") == "3.0.0"

    async def test_delegate_exists_for_every_version(self, service) -> None:
        kind = service.kind
        for version in ("1.0.0", "2.0.0", "3.0.0"):
            assert service.registry.delegate(kind, version) is not None


class TestConvergence:
    async def test_calls_converge_to_anchor_shape(self, service) -> None:
        results = dict(service.demo_calls())
        expected = {
            "city": "Berlin",
            "units": "celsius",
            "humidity": False,
            "wind": 0.0,
        }
        # Every registered version converges to the anchor handler's shape.
        for version in ("1.0.0", "2.0.0", "3.0.0"):
            assert results[version] == expected

    async def test_unversioned_payload_is_not_converged(self, service) -> None:
        assert service.registry.converge_payload({"foo": "bar"}) is None
