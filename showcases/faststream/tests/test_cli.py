"""CLI commands: configuration, send, and read."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from faststream_demo import cli
from faststream_demo.app.orders import ORDER_EXAMPLES
from typer.testing import CliRunner

runner = CliRunner()

BROKERS = [
    ("kafka", "kafka://localhost:9092"),
    ("rabbit", "amqp://guest:guest@localhost:5672/"),
    ("nats", "nats://localhost:4222"),
    ("redis", "redis://localhost:6379"),
]
BROKER_IDS = [broker for broker, _ in BROKERS]


class FakeBroker:
    """Minimal broker surface used by the CLI commands."""

    def __init__(self) -> None:
        self.published: list[tuple[dict[str, Any], str, dict[str, str]]] = []
        self.handler: Any = None
        self.payload: dict[str, Any] | None = None

    async def start(self) -> None:
        if self.handler is not None and self.payload is not None:
            await self.handler(self.payload)

    async def publish(
        self,
        payload: dict[str, Any],
        topic: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.published.append((payload, topic, headers or {}))

    def subscriber(self, topic: str):
        def decorate(handler: Any) -> Any:
            self.handler = handler
            return handler

        return decorate


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, FakeBroker]:
    container = MagicMock()
    container.init_resources = AsyncMock()
    container.shutdown_resources = AsyncMock()
    broker = FakeBroker()
    container.broker = AsyncMock(return_value=broker)
    monkeypatch.setattr(cli, "Container", lambda: container)
    return container, broker


@pytest.mark.parametrize(("broker_name", "dsn"), BROKERS, ids=BROKER_IDS)
def test_send_publishes_example(cli_env, broker_name, dsn) -> None:
    _, broker = cli_env

    result = runner.invoke(
        cli.app,
        [broker_name, dsn, "send", "orders.v1", "--example", "v1"],
    )

    assert result.exit_code == 0
    assert broker.published == [
        (ORDER_EXAMPLES["v1"], "orders.v1", {}),
    ]


@pytest.mark.parametrize(("broker_name", "dsn"), BROKERS, ids=BROKER_IDS)
def test_send_forwards_headers(cli_env, broker_name, dsn) -> None:
    _, broker = cli_env

    result = runner.invoke(
        cli.app,
        [
            broker_name,
            dsn,
            "send",
            "orders.v2",
            "--example",
            "v2",
            "--header",
            "accept-version=1.0.0",
            "--header",
            "trace=demo",
        ],
    )

    assert result.exit_code == 0
    assert broker.published[0][2] == {
        "accept-version": "1.0.0",
        "trace": "demo",
    }


@pytest.mark.parametrize(("broker_name", "dsn"), BROKERS, ids=BROKER_IDS)
def test_send_rejects_invalid_json(cli_env, broker_name, dsn) -> None:
    _, broker = cli_env

    result = runner.invoke(
        cli.app,
        [broker_name, dsn, "send", "orders.v1", "--payload", "{"],
    )

    assert result.exit_code != 0
    assert broker.published == []


@pytest.mark.parametrize(("broker_name", "dsn"), BROKERS, ids=BROKER_IDS)
def test_read_prints_payload(cli_env, broker_name, dsn) -> None:
    _, broker = cli_env
    broker.payload = ORDER_EXAMPLES["v1"]

    result = runner.invoke(
        cli.app,
        [
            broker_name,
            dsn,
            "read",
            "orders.v1",
            "--count",
            "1",
            "--timeout",
            "1",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output.strip().splitlines()[-1]) == ORDER_EXAMPLES["v1"]
