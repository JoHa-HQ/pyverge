"""Command-line entry point for the showcase.

uv run python -m fastmcp_demo          # self-driving demo
uv run python -m fastmcp_demo --serve  # run as an MCP server (stdio)
"""

from __future__ import annotations

import asyncio
import logging
import sys

from .container import build_container, resolve_prepared, shutdown_container
from .settings import DemoSettings

logger = logging.getLogger("fastmcp_demo")


def configure_logging(settings: DemoSettings) -> None:
    """Send logs to stderr — stdout is reserved for the MCP stdio protocol."""
    logging.basicConfig(
        level=settings.log_level.upper(),
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Third-party chatter (one line per HTTP call) — only useful when debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def _prepare():
    """Build the container, configure logging, and run the lifecycle once."""
    container = build_container()
    configure_logging(container.settings())
    service = await resolve_prepared(container)
    return container, service


def _serve() -> None:
    """Run the server over stdio. Runs outside asyncio so ``server.run`` can."""
    container, service = asyncio.run(_prepare())
    logger.info("Serving MCP over stdio")
    service.server.run()  # blocks on its own event loop
    asyncio.run(shutdown_container(container))


async def _demo() -> None:
    container, service = await _prepare()
    settings = container.settings()
    try:
        logger.info(
            "OTLP tracing ready; open http://localhost:16686 (service %s)",
            settings.telemetry.service_name,
        )
        kind = settings.graph.kind
        logger.info("Older calls converge to the anchor handler:")
        for version, result in await service.demo_calls():
            logger.info("  %s@%s -> %s", kind, version, result)
    finally:
        await shutdown_container(container)


def main() -> None:
    if "--serve" in sys.argv:
        _serve()
    else:
        asyncio.run(_demo())


if __name__ == "__main__":
    main()
