from __future__ import annotations

import argparse
from collections.abc import AsyncIterator
from typing import Any

import pytest
import semver
from faststream import FastStream
from faststream.kafka import TestKafkaBroker
from faststream.nats import TestNatsBroker
from faststream.rabbit import TestRabbitBroker
from faststream.redis import TestRedisBroker
from faststream_demo.app.container import Container
from faststream_demo.app.orders import ORDER_TOPICS
from faststream_demo.cli import Broker

from pyverge import Manager

TEST_BROKERS: dict[Broker, type] = {
    Broker.KAFKA: TestKafkaBroker,
    Broker.RABBITMQ: TestRabbitBroker,
    Broker.NATS: TestNatsBroker,
    Broker.REDIS: TestRedisBroker,
}


def pytest_addoption(parser: pytest.Parser) -> None:
    """Mirror the Typer entrypoint's options for test runs."""
    group = parser.getgroup("faststream showcase")
    group.addoption(
        "--broker",
        action="store",
        default=Broker.KAFKA.value,
        choices=tuple(broker.value for broker in Broker),
        help="Broker alias (default: kafka).",
    )
    group.addoption(
        "--dsn",
        action="store",
        default=None,
        help="Broker DSN; use with the CLI send/read commands.",
    )
    group.addoption(
        "--topic",
        dest="topics",
        action="append",
        default=None,
        help="Input topic; repeat for multiple channels.",
    )
    group.addoption(
        "--policy",
        action="store",
        default="latest",
        help="Convergence target policy.",
    )
    group.addoption(
        "--version-header",
        action="store",
        default="accept-version",
        help="Version negotiation header.",
    )
    group.addoption(
        "--telemetry",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Enable OTLP tracing.",
    )
    group.addoption(
        "--service-name",
        action="store",
        default="pyverge-faststream-demo",
        help="OTLP service name.",
    )
    group.addoption(
        "--otlp-endpoint",
        action="store",
        default="http://localhost:4317",
        help="OTLP collector endpoint.",
    )


@pytest.fixture
def broker_kind(request: pytest.FixtureRequest) -> Broker:
    return Broker(request.config.getoption("broker"))


@pytest.fixture
async def container(
    request: pytest.FixtureRequest, broker_kind: Broker
) -> AsyncIterator[Container]:
    """Build the real container from the pytest options, tracing off."""
    container = Container()
    container.config.broker.factory.from_value(broker_kind.broker)
    container.config.broker.telemetry.middleware.from_value(broker_kind.telemetry)
    container.config.broker.dsn.from_value(request.config.getoption("dsn"))
    container.config.broker.topics.from_value(
        request.config.getoption("topics") or list(ORDER_TOPICS)
    )
    container.config.broker.convergence.target.from_value(
        request.config.getoption("policy")
    )
    container.config.broker.convergence.header.from_value(
        request.config.getoption("version_header")
    )
    container.config.telemetry.enabled.from_value(request.config.getoption("telemetry"))
    container.config.telemetry.service_name.from_value(
        request.config.getoption("service_name")
    )
    container.config.telemetry.endpoint.from_value(
        request.config.getoption("otlp_endpoint")
    )
    container.config.migration.direction.from_value("any")
    container.config.migration.on_missing.from_value("reconstruct_model")
    container.config.migration.version_property.from_value("version")
    container.config.migration.kind_property.from_value("kind")
    await container.init_resources()
    try:
        yield container
    finally:
        await container.shutdown_resources()


@pytest.fixture
async def app(container: Container) -> FastStream:
    """The assembled app: Order feature wired, tracing off."""
    return await container.application()


@pytest.fixture
def broker(app: FastStream) -> Any:
    return app.context.context["broker"]


@pytest.fixture
def manager(app: FastStream) -> Manager[semver.Version]:
    return app.context.context["manager"]


@pytest.fixture
def test_broker(broker_kind: Broker) -> type:
    return TEST_BROKERS[broker_kind]
