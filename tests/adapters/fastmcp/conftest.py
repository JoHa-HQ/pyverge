"""End-to-end fixtures for the FastMCP adapter suites.

Registration and model shapes come from the shared fixtures in
``tests/conftest.py`` (``model_adapter`` / ``registry`` / ``manager``). The
``app`` fixture builds a test FastMCP server whose lifespan runs the discovery
lifecycle; the async ``client`` fixture wraps it in a live session, so each test
case drives the public client surface. No internal wiring is assembled by the
tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

import pytest
from fastmcp import Client, FastMCP

from pyverge.adapters.fastmcp import ToolDiscovery, ToolReflection


@dataclass(frozen=True)
class Case:
    """A physical tool plus the call that must converge through it.

    Parametrize the ``case`` fixture (indirectly) with a :class:`Case`; the
    ``app`` fixture materializes its tool and the test drives ``client``.
    ``call_version`` is negotiated natively (FastMCP's ``version=``).
    """

    id: str
    kind: str
    handler: Callable[..., Any]
    version: str | None = None
    policies: dict[str, str] = field(default_factory=dict)
    policy: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)
    call_version: str | None = None


@pytest.fixture
def case(request: pytest.FixtureRequest) -> Case:
    """The parametrized app/call case (set via indirect parametrize)."""
    return request.param


@pytest.fixture
def app(request: pytest.FixtureRequest, manager: type, case: Case) -> FastMCP:
    """A test FastMCP server whose lifespan runs the discovery lifecycle.

    The physical tool and its policy come from *case*; FastMCP enters the
    lifespan when the ``client`` fixture opens its session.
    """
    instance = manager()
    discovery = ToolDiscovery(
        instance, [ToolReflection(instance.adapter)], policies=case.policies
    )

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        await discovery.search(server)
        discovery.register()
        await discovery.enrich(server)
        yield {"discovery": discovery}

    server = FastMCP("TestServer", lifespan=app_lifespan)
    meta = {"policy": case.policy} if case.policy else None
    server.tool(case.handler, name=case.kind, version=case.version, meta=meta)
    return server


@pytest.fixture
async def client(app: FastMCP) -> AsyncIterator[Client]:
    """A live client session over *app*, so the lifespan runs per test."""
    async with Client(app) as active:
        yield active
