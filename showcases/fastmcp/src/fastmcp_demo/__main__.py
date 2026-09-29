"""Single entry point — serve the MCP server over HTTP.

    uv run python -m fastmcp_demo

One async entry point: build the container, run the reflection lifecycle, then
serve MCP over HTTP. HTTP (not stdio) keeps the entry point a plain coroutine —
no second event loop — and lets a code agent connect with a URL.

Tests do not use this module: they build the same app through the composition
root and drive it in-process (see ``tests/conftest.py``).
"""

from __future__ import annotations

import asyncio
import logging

from .container import build_container, resolve_prepared, shutdown_container
from .settings import DemoSettings

logger = logging.getLogger("fastmcp_demo")


def configure_logging(settings: DemoSettings) -> None:
    """Configure root logging and quiet noisy third-party loggers."""
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Third-party chatter (one line per HTTP call) — only useful when debugging.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


async def serve() -> None:
    """Build the app and serve it over HTTP until interrupted."""
    container = build_container()
    settings = container.settings()
    configure_logging(settings)
    service = await resolve_prepared(container)

    bind = settings.server
    logger.info(
        "OTLP tracing ready; open http://localhost:16686 (service %s)",
        settings.telemetry.service_name,
    )
    logger.info("Serving MCP over http://%s:%d%s", bind.host, bind.port, bind.path)
    try:
        await service.server.run_async(
            transport="http",
            host=bind.host,
            port=bind.port,
            path=bind.path,
            show_banner=False,
        )
    finally:
        await shutdown_container(container)


def main() -> None:
    asyncio.run(serve())


if __name__ == "__main__":
    main()
