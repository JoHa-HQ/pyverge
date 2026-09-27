"""Command-line entry point for the showcase.

PYTHONPATH=showcases/fastmcp/src uv run python -m fastmcp_demo          # demo
PYTHONPATH=showcases/fastmcp/src uv run python -m fastmcp_demo --serve  # server
"""

from __future__ import annotations

import asyncio
import sys

from .application.service import walk_topology
from .container import build_container
from .domain import ALL_VERSIONS


def main() -> None:
    """Compose the container, prepare the server, then run the chosen mode."""
    container = build_container()
    settings = container.settings()
    service = container.demo_service()

    print(
        "OTLP tracing enabled; open http://localhost:16686 (service "
        f"{settings.telemetry.service_name})"
    )

    asyncio.run(service.prepare())

    if "--serve" in sys.argv:
        print("Running the MCP server (Ctrl-C to stop)")
        assert service.server is not None
        service.server.run()
        return

    kind = settings.graph.kind
    print("Self-driving demo — older calls converge to the anchor handler:")
    for version, result in service.demo_calls():
        print(f"  {kind}@{version:6s} -> {result}")

    print("Topology walk (time travel down and back):")
    for hop in walk_topology(service.manager, kind, ALL_VERSIONS):
        print(f"  {hop.version:6s} -> {hop.payload}")


if __name__ == "__main__":
    main()
