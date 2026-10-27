# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""FastMCP source descriptor traversal."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
import semver
from fastmcp import FastMCP

from pyverge.adapters.fastmcp import (
    FastMCPSource,
    PromptReflection,
    ResourceReflection,
    ToolReflection,
)
from pyverge.discovery import RegistrationCollector
from pyverge.schemas import ModelCodec, PydanticModelAdapter

pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def loop() -> Any:
    event_loop = asyncio.new_event_loop()
    yield event_loop
    event_loop.close()


@pytest.fixture(scope="module")
def source() -> FastMCPSource:
    adapter = PydanticModelAdapter[semver.Version](codec=ModelCodec())
    server = FastMCP("source-bench")

    @server.tool(name="User", version="2.0.0")
    def handler(name: str) -> dict[str, Any]:
        return {"name": name}

    return FastMCPSource(
        server,
        providers=(
            ToolReflection(adapter),
            PromptReflection(adapter),
            ResourceReflection(adapter),
        ),
    )


def test_source_descriptors(benchmark: Any, loop: Any, source: FastMCPSource) -> None:
    def collect() -> list[Any]:
        collector = RegistrationCollector()
        loop.run_until_complete(source.accept(collector))
        return collector.commands

    commands = benchmark(collect)

    assert len(commands) == 1
