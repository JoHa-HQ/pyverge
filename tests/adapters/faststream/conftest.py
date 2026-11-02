# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared fixtures for the FastStream adapter suites.

The version graph comes from the shared ``registry`` fixture in
``tests/conftest.py`` (parametrized indirectly per test). Tests drive the public
broker surface with FastStream's ``TestKafkaBroker`` — an in-memory broker, no
Kafka container.
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from faststream.kafka import KafkaBroker

from pyverge.adapters.faststream import subscriber
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
