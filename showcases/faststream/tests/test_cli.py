"""CLI configuration: Typer validates the broker alias."""

from __future__ import annotations

import pytest
from faststream_demo.cli import Broker, cli
from typer.testing import CliRunner

runner = CliRunner()


def test_help_lists_options() -> None:
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "--topic" in result.output


def test_invalid_broker_is_rejected() -> None:
    result = runner.invoke(cli, ["bogus", "kafka://localhost:9092"])
    assert result.exit_code != 0


@pytest.mark.parametrize(
    ("key", "name"),
    [
        ("kafka", "KafkaBroker"),
        ("rabbit", "RabbitBroker"),
        ("nats", "NatsBroker"),
        ("redis", "RedisBroker"),
    ],
)
def test_broker_alias_resolves_to_class(key: str, name: str) -> None:
    assert Broker(key).broker.__name__ == name
