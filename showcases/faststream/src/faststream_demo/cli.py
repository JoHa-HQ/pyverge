"""FastStream + pyverge showcase — Typer entrypoint.

The broker is resolved on the command call; the container builds the settings,
broker, tracer, app, and wires the Order feature.
"""

from __future__ import annotations

import asyncio
import importlib
from enum import StrEnum
from functools import cached_property, wraps
from typing import Annotated

import typer
from faststream.opentelemetry import TelemetryMiddleware
from pydantic import AmqpDsn, KafkaDsn, NatsDsn, RedisDsn

from .app.container import Container
from .app.orders import ORDER_TOPICS


class Broker(StrEnum):
    """Broker alias; its value maps to the FastStream module."""

    KAFKA = "kafka"
    RABBITMQ = "rabbit"
    NATS = "nats"
    REDIS = "redis"

    @cached_property
    def broker(self):
        klass = f"{self.value.capitalize()}Broker"
        return getattr(importlib.import_module(f"faststream.{self.value}.broker"), klass)

    @cached_property
    def telemetry(self) -> TelemetryMiddleware:
        klass = f"{self.value.capitalize()}TelemetryMiddleware"
        module = importlib.import_module(f"faststream.{self.value}.opentelemetry")
        return getattr(module, klass)


def resolve_dsn(
    ctx: typer.Context, value: str
) -> RedisDsn | KafkaDsn | NatsDsn | AmqpDsn:
    match ctx.params["broker"]:
        case Broker.KAFKA:
            return KafkaDsn(value)
        case Broker.RABBITMQ:
            return AmqpDsn(value)
        case Broker.REDIS:
            return RedisDsn(value)
        case Broker.NATS:
            return NatsDsn(value)
        case _:
            raise ValueError(value)


cli = typer.Typer(add_completion=False)


@cli.command()
@lambda f: wraps(f)(lambda *a, **kw: asyncio.run(f(*a, **kw)))
async def run(  # noqa: PLR0913
    broker: Annotated[Broker, typer.Argument(help="kafka | rabbitmq | nats | redis.")],
    dsn: Annotated[str, typer.Argument(callback=resolve_dsn)],
    topic: Annotated[str, typer.Option(help="Comma-separated topics.")] = ",".join(
        ORDER_TOPICS
    ),
    policy: Annotated[str, typer.Option()] = "latest",
    otlp_endpoint: Annotated[str, typer.Option()] = "http://localhost:4317",
    service_name: Annotated[str, typer.Option()] = "pyverge-faststream-demo",
) -> None:
    """Run the showcase against the chosen broker."""
    container = Container()
    container.config.broker.factory.from_value(broker.broker)
    container.config.broker.telemetry.middleware.from_value(broker.telemetry)
    container.config.broker.dsn.from_value(str(dsn))
    container.config.broker.topics.from_value([t.strip() for t in topic.split(",")])
    container.config.broker.convergence.target.from_value(policy)

    container.config.telemetry.enabled.from_value(True)
    container.config.telemetry.service_name.from_value(service_name)
    container.config.telemetry.endpoint.from_value(str(otlp_endpoint))

    container.config.migration.direction.from_value("any")
    container.config.migration.on_missing.from_value("reconstruct_model")
    container.config.migration.version_property.from_value("version")
    container.config.migration.kind_property.from_value("kind")

    await container.init_resources()
    try:
        application = await container.application()
        await application.run()
    finally:
        await container.shutdown_resources()


__all__ = ["cli", "run"]
