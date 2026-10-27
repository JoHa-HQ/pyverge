"""FastStream source descriptor traversal."""

from __future__ import annotations

from typing import Any

import pytest
import semver
from faststream import FastStream
from faststream.kafka import KafkaBroker

from pyverge.adapters.faststream import FastStreamSource, subscriber
from pyverge.discovery import RegistrationCollector
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from tests.benchmarks.graphs import user_manager
from tests.examples.pydantic.semver import UserV2

pytestmark = pytest.mark.benchmark


@pytest.fixture(scope="module")
def source() -> FastStreamSource:
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "bench-source", manager=user_manager(), targets="latest")
    async def handle(user: UserV2) -> None: ...

    return FastStreamSource(
        FastStream(broker),
        adapter=PydanticModelAdapter[semver.Version](codec=ModelCodec()),
    )


def test_source_descriptors(benchmark: Any, source: FastStreamSource) -> None:
    def collect() -> list[Any]:
        collector = RegistrationCollector()
        source.accept(collector)
        return collector.commands

    commands = benchmark(collect)

    assert len(commands) == 1
