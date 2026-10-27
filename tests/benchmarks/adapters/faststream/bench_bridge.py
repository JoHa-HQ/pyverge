# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""FastStream in/out bridge: consume at ``latest``, produce at ``1.0.0``."""

from __future__ import annotations

from typing import Any

import pytest
from faststream.kafka import KafkaBroker, TestKafkaBroker

from pyverge.adapters.faststream import publisher, subscriber
from tests.benchmarks.adapters.faststream._support import new_loop, run
from tests.benchmarks.factories import payloads
from tests.benchmarks.graphs import user_manager
from tests.examples.pydantic.semver import UserV3

pytestmark = pytest.mark.benchmark

IN_TOPIC = "in"
OUT_TOPIC = "out"


@pytest.fixture(scope="module")
def loop() -> Any:
    event_loop = new_loop()
    yield event_loop
    event_loop.close()


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    return payloads(user_manager(), "User", "1.0.0", count=1)[0]


def test_bridge(benchmark: Any, loop: Any, payload: dict) -> None:
    manager = user_manager()
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, IN_TOPIC, manager=manager, targets="latest")
    @publisher(broker, OUT_TOPIC, manager=manager, target="1.0.0")
    async def handle(user: UserV3) -> UserV3:
        return user

    @broker.subscriber(OUT_TOPIC)
    async def sink(message: dict) -> None: ...

    broker_test = TestKafkaBroker(broker)
    active = run(loop, broker_test.__aenter__())
    try:
        benchmark(lambda: run(loop, active.publish(payload, IN_TOPIC)))
    finally:
        run(loop, broker_test.__aexit__(None, None, None))
