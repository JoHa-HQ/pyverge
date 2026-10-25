"""Shared fixtures for the FastStream adapter suites.

The version graph comes from the shared ``registry`` fixture in
``tests/conftest.py`` (parametrized indirectly per test). Tests drive the public
broker surface with FastStream's ``TestKafkaBroker`` — an in-memory broker, no
Kafka container.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
import semver
from faststream import FastStream
from faststream.kafka import KafkaBroker

from pyverge import Manager
from pyverge.adapters.faststream import FastStreamSource, subscriber
from tests.examples.pydantic.semver import UserV2

KAFKA_BROKER: tuple[type[Any], dict[str, Any], str | dict[str, str]] = (
    KafkaBroker,
    {"bootstrap_servers": "localhost:9092"},
    "latest",
)


@pytest.fixture(params=[KAFKA_BROKER], ids=["kafka"])
def broker(request, manager) -> KafkaBroker:
    """A broker whose ``users`` subscriber converges through a fresh manager.

    Fixture params carry the broker implementation, constructor settings, and
    target policy.
    """
    broker_cls, settings, target = request.param
    instance = manager()
    broker = cast(Any, broker_cls(**settings))
    broker.payloads = []

    @subscriber(broker, "users", manager=instance, targets=target)
    async def handle(user: UserV2) -> None:
        broker.payloads.append(user.model_dump())

    return broker


@pytest.fixture
def source(model_adapter) -> FastStreamSource:
    subscriber_manager = Manager[semver.Version].configure(model_adapter)
    subscriber_manager.store_model(UserV2)
    instance = subscriber_manager()
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "source-users", manager=instance)
    async def handle(user: UserV2) -> None: ...

    return FastStreamSource(FastStream(broker), adapter=model_adapter)


@pytest.fixture
def publisher_source(model_adapter) -> FastStreamSource:
    broker = KafkaBroker("localhost:9092")

    @broker.publisher("source-out")
    def emit(user: UserV2) -> UserV2:
        return user

    return FastStreamSource(FastStream(broker), adapter=model_adapter)
