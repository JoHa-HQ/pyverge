# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""FastStream consume path: publish → decoder convergence → handler.

Two benchmarks share the same broker and payload:

* ``test_consume_with_pyverge`` — a converging ``subscriber`` (converges v1 → v3).
* ``test_consume_baseline`` — a plain FastStream subscriber (no pyverge).

The delta isolates the adapter's per-message cost from FastStream's own overhead.
Payloads are synthesized and validated via ``tests.benchmarks.factories``.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from faststream.kafka import KafkaBroker, TestKafkaBroker

from pyverge.adapters.faststream import subscriber
from tests.benchmarks.adapters.faststream._support import new_loop, run
from tests.benchmarks.factories import payloads
from tests.benchmarks.graphs import user_manager
from tests.examples.pydantic.semver import UserV3

pytestmark = pytest.mark.benchmark

TOPIC = "bench"


@pytest.fixture(scope="module")
def loop() -> Any:
    event_loop = new_loop()
    yield event_loop
    event_loop.close()


@pytest.fixture(scope="module")
def payload() -> dict[str, Any]:
    return payloads(user_manager(), "User", "1.0.0", count=1)[0]


def _bench_publish(
    benchmark: Any, loop: asyncio.AbstractEventLoop, broker: KafkaBroker, payload: dict
) -> None:
    broker_test = TestKafkaBroker(broker)
    active = run(loop, broker_test.__aenter__())
    try:
        benchmark(lambda: run(loop, active.publish(payload, TOPIC)))
    finally:
        run(loop, broker_test.__aexit__(None, None, None))


def test_consume_with_pyverge(benchmark: Any, loop: Any, payload: dict) -> None:
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, TOPIC, manager=user_manager(), targets="latest")
    async def handle(user: UserV3) -> None: ...

    _bench_publish(benchmark, loop, broker, payload)


def test_consume_baseline(benchmark: Any, loop: Any, payload: dict) -> None:
    broker = KafkaBroker("localhost:9092")

    @broker.subscriber(TOPIC)
    async def handle(message: dict) -> None: ...

    _bench_publish(benchmark, loop, broker, payload)
