"""Showcase fixtures: assemble the app and drive it over an in-memory broker."""

from __future__ import annotations

import pytest
from faststream import FastStream
from faststream.kafka import KafkaBroker

from faststream_demo.app.orders import OrdersFeature
from faststream_demo.app.orders.domain import configure_manager
from faststream_demo.app.resource import build_faststream
from pyverge.migration import MigrationSettings

SETTINGS = MigrationSettings(
    direction="any",
    on_missing="reconstruct_model",
    version_property="version",
    kind_property="kind",
)


@pytest.fixture
def app() -> FastStream:
    """The assembled app: Order feature wired, tracing off."""
    broker = KafkaBroker()
    return build_faststream(
        "test",
        broker,
        configure_manager(SETTINGS),
        None,
        [OrdersFeature()],
    )


@pytest.fixture
def broker(app: FastStream) -> KafkaBroker:
    return app.brokers[0]


@pytest.fixture
def manager(app: FastStream):
    return app.context.context["manager"]
