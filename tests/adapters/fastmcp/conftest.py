# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""End-to-end fixtures for the FastMCP adapter suites.

Registration and model shapes come from the shared fixtures in
``tests/conftest.py`` (``model_adapter`` / ``registry`` / ``manager``). The
``app`` fixture attaches a provider to a real FastMCP server; the async
``client`` fixture opens a session, so every test drives the public client
surface and the provider lifespan.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from fastmcp import Client, FastMCP
from fastmcp_case import SOURCE_CASE, Case

from pyverge.adapters.fastmcp import PyvergeProvider


@pytest.fixture(params=[SOURCE_CASE], ids=["source"])
def case(request: pytest.FixtureRequest) -> Case:
    """The parametrized app/call case; defaults to the source case."""
    return request.param


@pytest.fixture
def app(request: pytest.FixtureRequest, manager: type, case: Case) -> FastMCP:
    """A FastMCP server with the provider attached.

    The physical tool and its policy come from *case*; FastMCP enters the
    provider lifespan when the ``client`` fixture opens its session.
    """
    instance = manager()
    discovery = PyvergeProvider(
        instance,
        policies=case.policies,
        virtual_versions=True,
    )
    server = FastMCP("TestServer", providers=[discovery])
    server.tool(case.handler, name=case.kind, version=case.version)
    return server


@pytest.fixture
async def client(app: FastMCP) -> AsyncIterator[Client]:
    """A live client session over *app*, so the lifespan runs per test."""
    async with Client(app) as active:
        yield active
