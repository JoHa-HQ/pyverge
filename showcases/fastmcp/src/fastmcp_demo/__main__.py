"""Command-line entry point for the showcase.

cd showcases/fastmcp
uv run python -m fastmcp_demo          # self-driving demo
uv run python -m fastmcp_demo --serve  # run the MCP server
"""

from __future__ import annotations

import asyncio
import sys

from .container import build_container, resolve_prepared, shutdown_container


async def _run() -> None:
    container = build_container()
    settings = container.settings()

    if settings.telemetry.enabled:
        print(
            "OTLP tracing enabled; open http://localhost:16686 (service "
            f"{settings.telemetry.service_name})"
        )
    else:
        print("OTLP tracing disabled (FASTMCP_DEMO_TELEMETRY__ENABLED=false)")

    try:
        # ``resolve_prepared`` runs the reflection lifecycle once.
        service = await resolve_prepared(container)

        if "--serve" in sys.argv:
            print("Running the MCP server (Ctrl-C to stop)")
            service.server.run()
            return

        kind = settings.graph.kind
        print("Self-driving demo — older calls converge to the anchor handler:")
        for version, result in service.demo_calls():
            print(f"  {kind}@{version:6s} -> {result}")
    finally:
        await shutdown_container(container)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
