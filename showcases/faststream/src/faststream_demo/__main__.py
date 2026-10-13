"""Run the showcase against the configured broker.

Selects the broker from settings, attaches the per-migration OpenTelemetry hooks
to the manager, and runs the FastStream app. Set ``FASTSTREAM_DEMO__BROKER__NAME``
to ``kafka`` (default), ``rabbitmq``, ``nats``, or ``redis``.
"""

from __future__ import annotations

import asyncio
import logging

from .adapters import build_app, build_tracer_provider, make_migration_hooks
from .domain import build_manager
from .settings import DemoSettings


def main() -> None:
    settings = DemoSettings()
    logging.basicConfig(level=settings.log_level)

    provider = build_tracer_provider(settings.telemetry)
    manager = build_manager()
    manager.attach_hooks(
        make_migration_hooks(provider, settings.telemetry.service_name)
    )

    app = build_app(manager, settings.broker, provider)
    asyncio.run(app.run())


if __name__ == "__main__":
    main()
