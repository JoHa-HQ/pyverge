from __future__ import annotations

import asyncio
import importlib
import json
from enum import StrEnum
from functools import cached_property, wraps
from pathlib import Path
from typing import Annotated, Any

import typer
from faststream.opentelemetry import TelemetryMiddleware
from pydantic import AmqpDsn, KafkaDsn, NatsDsn, RedisDsn

from .app.container import Container
from .app.orders import MICROCKS_TOPICS, ORDER_EXAMPLES, ORDER_TOPICS


class Broker(StrEnum):
    """Broker alias; its value maps to the FastStream module."""

    KAFKA = "kafka"
    RABBITMQ = "rabbit"
    NATS = "nats"
    REDIS = "redis"

    @cached_property
    def broker(self):
        klass = f"{self.value.capitalize()}Broker"
        return getattr(
            importlib.import_module(f"faststream.{self.value}.broker"), klass
        )

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


app = typer.Typer(add_completion=False)


def _parse_headers(values: list[str] | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    for item in values or ():
        key, separator, value = item.partition("=")
        if not separator or not key.strip():
            raise typer.BadParameter(f"expected key=value header, got {item!r}")
        headers[key.strip()] = value.strip()
    return headers


def _load_payload(
    payload: str | None,
    path: Path | None,
    example: str | None,
) -> dict[str, Any]:
    if example is not None:
        try:
            return ORDER_EXAMPLES[example.lower()]
        except KeyError as exc:
            names = ", ".join(ORDER_EXAMPLES)
            raise typer.BadParameter(
                f"unknown example {example!r}; use {names}"
            ) from exc
    if payload is not None:
        source = payload
    elif path is not None:
        source = path.read_text(encoding="utf-8")
    else:
        raise typer.BadParameter("pass --payload, --file, or --example")
    try:
        value = json.loads(source)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise typer.BadParameter("payload must be a JSON object")
    return value


@app.callback()
def configure(  # noqa: PLR0913, PLR0917
    ctx: typer.Context,
    broker: Annotated[Broker, typer.Argument(...)],
    dsn: Annotated[str, typer.Argument(callback=resolve_dsn)],
    topics: Annotated[
        list[str],
        typer.Option("--topic", help="Repeat for multiple channels."),
    ] = list(ORDER_TOPICS),
    policy: Annotated[str, typer.Option()] = "latest",
    otlp_endpoint: Annotated[str, typer.Option()] = "http://localhost:4317",
    service_name: Annotated[str, typer.Option()] = "pyverge-faststream-demo",
    telemetry: Annotated[bool, typer.Option("--telemetry/--no-telemetry")] = True,
    microcks: Annotated[bool, typer.Option("--microcks/--no-microcks")] = False,
    version_header: Annotated[
        str | None,
        typer.Option("--version-header", help="Version negotiation header."),
    ] = "accept-version",
) -> None:
    if microcks:
        topics = list(MICROCKS_TOPICS)
    container = Container()
    container.config.broker.factory.from_value(broker.broker)
    container.config.broker.telemetry.middleware.from_value(broker.telemetry)
    container.config.broker.dsn.from_value(str(dsn))
    container.config.broker.topics.from_value(topics)
    container.config.broker.convergence.target.from_value(policy)
    container.config.broker.convergence.header.from_value(version_header)
    container.config.telemetry.enabled.from_value(telemetry)
    container.config.telemetry.service_name.from_value(service_name)
    container.config.telemetry.endpoint.from_value(str(otlp_endpoint))
    container.config.migration.direction.from_value("any")
    container.config.migration.on_missing.from_value("reconstruct_model")
    container.config.migration.version_property.from_value("version")
    container.config.migration.kind_property.from_value("kind")
    ctx.obj = container


@app.command()
@lambda f: wraps(f)(lambda *a, **kw: asyncio.run(f(*a, **kw)))
async def send(  # noqa: PLR0913, PLR0917
    ctx: typer.Context,
    topic: Annotated[str, typer.Argument(help="Destination topic.")],
    payload: Annotated[
        str | None,
        typer.Option("--payload", "-p", help="Inline JSON payload."),
    ] = None,
    path: Annotated[
        Path | None,
        typer.Option("--file", "-f", help="JSON payload file."),
    ] = None,
    example: Annotated[
        str | None,
        typer.Option("--example", help="Built-in v1 or v2 event."),
    ] = None,
    headers: Annotated[
        list[str] | None,
        typer.Option("--header", "-H", help="Repeat key=value header."),
    ] = None,
) -> None:
    """Publish one JSON payload to a broker topic."""
    event = _load_payload(payload, path, example)
    container: Container = ctx.obj
    await container.init_resources()
    try:
        broker = await container.broker()
        await broker.start()
        await broker.publish(event, topic, headers=_parse_headers(headers))
        typer.echo(f"published {topic}")
    finally:
        await container.shutdown_resources()


@app.command()
@lambda f: wraps(f)(lambda *a, **kw: asyncio.run(f(*a, **kw)))
async def read(
    ctx: typer.Context,
    topic: Annotated[str, typer.Argument(help="Source topic.")],
    count: Annotated[int, typer.Option("--count", "-n", min=1)] = 1,
    timeout: Annotated[float, typer.Option("--timeout", min=0.1)] = 30.0,
) -> None:
    """Read payloads from a broker topic and print them as JSON."""
    seen: list[dict[str, Any]] = []

    async def capture(payload: dict[str, Any]) -> None:
        seen.append(payload)

    container: Container = ctx.obj
    await container.init_resources()
    try:
        broker = await container.broker()
        broker.subscriber(topic)(capture)
        await broker.start()
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while len(seen) < count and loop.time() < deadline:
            await asyncio.sleep(0.1)
    finally:
        await container.shutdown_resources()

    for item in seen[:count]:
        typer.echo(json.dumps(item))
    if not seen:
        raise typer.Exit(code=1)


@app.command()
@lambda f: wraps(f)(lambda *a, **kw: asyncio.run(f(*a, **kw)))
async def run(ctx: typer.Context):
    container = ctx.obj
    await container.init_resources()
    try:
        application = await container.application()
        await application.run()
    finally:
        await container.shutdown_resources()


__all__ = ["app", "read", "run", "send"]
