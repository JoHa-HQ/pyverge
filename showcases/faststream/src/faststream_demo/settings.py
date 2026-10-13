"""Configuration for the FastStream showcase.

Nested pydantic-settings models, mirroring the layout used across the codebase:
each concern is a ``BaseSettings`` with its own ``env_prefix`` and
``env_nested_delimiter="__"`` so the tree reads cleanly from environment
variables (e.g. ``FASTSTREAM_DEMO__BROKER__NAME``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Per-broker connection defaults; a broker's own URL scheme differs.
DEFAULT_SERVERS = {
    "kafka": "localhost:9092",
    "rabbitmq": "amqp://guest:guest@localhost:5672/",
    "nats": "nats://localhost:4222",
    "redis": "redis://localhost:6379",
}


class BrokerSettings(BaseSettings):
    """Which broker to run against and how to reach it."""

    name: str = Field(
        default="kafka",
        description="One of kafka, rabbitmq, nats, redis.",
    )
    servers: str | None = Field(
        default=None,
        description="Connection string; defaults per broker when unset.",
    )
    target: str = Field(
        default="latest",
        description="Convergence target policy for the consumer.",
    )

    model_config = SettingsConfigDict(env_prefix="BROKER_", extra="ignore")

    @property
    def url(self) -> str:
        """The connection string, defaulting per selected broker."""
        return self.servers or DEFAULT_SERVERS[self.name]


class TelemetrySettings(BaseSettings):
    """OpenTelemetry tracing configuration."""

    enabled: bool = Field(
        default=True,
        description="Build an OTLP tracer. False keeps the app export-free (tests).",
    )
    service_name: str = Field(default="pyverge-faststream-demo")
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP gRPC collector endpoint.",
    )

    model_config = SettingsConfigDict(env_prefix="TELEMETRY_", extra="ignore")


class DemoSettings(BaseSettings):
    """Root settings for the showcase application."""

    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    log_level: str = Field(
        default="INFO",
        description="Root log level for the demo (e.g. DEBUG, INFO, WARNING).",
    )

    model_config = SettingsConfigDict(
        env_prefix="FASTSTREAM_DEMO_",
        env_nested_delimiter="__",
        extra="ignore",
    )
