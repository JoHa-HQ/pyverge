"""Command-line entry point for the showcase.

uv run python -m fastmcp_demo          # self-driving demo
uv run python -m fastmcp_demo --serve  # run as an MCP server (stdio)
"""

from __future__ import annotations

import asyncio
import sys

from .container import build_container, resolve_prepared, shutdown_container


async def _prepare():
    """Build the container and run the reflection lifecycle once."""
    container = build_container()
    service = await resolve_prepared(container)
    return container, service


def _serve() -> None:
    """Run the server over stdio. Runs outside asyncio so ``server.run`` can.

    Diagnostics go to stderr — stdout carries the MCP protocol.
    """
    container, service = asyncio.run(_prepare())
    print("Serving MCP over stdio", file=sys.stderr)
    service.server.run()  # blocks on its own event loop
    asyncio.run(shutdown_container(container))


async def _demo() -> None:
    container, service = await _prepare()
    settings = container.settings()
    try:
        print(
            "OTLP tracing enabled; open http://localhost:16686 (service "
            f"{settings.telemetry.service_name})"
        )
        kind = settings.graph.kind
        print("Self-driving demo — older calls converge to the anchor handler:")
        for version, result in await service.demo_calls():
            print(f"  {kind}@{version:6s} -> {result}")
    finally:
        await shutdown_container(container)


def main() -> None:
    if "--serve" in sys.argv:
        _serve()
    else:
        asyncio.run(_demo())


if __name__ == "__main__":
    main()
